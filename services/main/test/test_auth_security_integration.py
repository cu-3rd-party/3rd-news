from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import cast

import pytest
from fastapi import HTTPException, Request, Response
from lib.core.config import Settings
from lib.dto.requests import LoginRequest
from lib.handlers.auth import _authenticated_user, login
from lib.infra.clients.auth import AuthService
from lib.infra.storage.postgres.database import Database
from lib.infra.storage.postgres.models import ApiKey, AuthRateLimit, Session, User
from lib.infra.storage.postgres.repositories import AuthAccountRepository
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from test.settings import get_test_settings

pytestmark = pytest.mark.integration


def _request(auth: AuthService, settings: Settings, *, ip_address: str) -> Request:
    return cast(
        Request,
        SimpleNamespace(
            app=SimpleNamespace(state=SimpleNamespace(auth=auth, settings=settings)),
            headers={},
            client=SimpleNamespace(host=ip_address),
        ),
    )


async def test_normalized_account_and_ip_are_durably_rate_limited(
    integration_database, monkeypatch
) -> None:
    identity = uuid.uuid4().hex
    email = f"qa-{identity}@example.edu"
    ip_address = f"qa-client-{identity}"
    auth = AuthService(private_key="", public_key="", password_verify_concurrency=1)
    password_hash = auth.hash_password("correct horse battery staple")
    settings = Settings(
        auth_login_attempt_limit=2,
        auth_login_window_seconds=600,
        auth_login_base_cooldown_seconds=60,
        auth_login_max_cooldown_seconds=60,
    )
    async with integration_database() as session, session.begin():
        session.add(User(email=email, password_hash=password_hash, role="editor"))

    for attempted_email in (email.upper(), email):
        async with integration_database() as session:
            with pytest.raises(HTTPException) as rejected:
                await _authenticated_user(
                    LoginRequest(email=attempted_email, password="definitely wrong"),
                    _request(auth, settings, ip_address=ip_address),
                    AuthAccountRepository(session),
                )
            assert rejected.value.status_code == 401
            assert rejected.value.detail == "invalid credentials"

    def should_not_verify(_password: str, _encoded: str | None) -> bool:
        raise AssertionError("blocked credentials must not consume Argon2 capacity")

    monkeypatch.setattr(auth, "verify_password", should_not_verify)
    async with integration_database() as session:
        with pytest.raises(HTTPException) as blocked:
            await _authenticated_user(
                LoginRequest(email=email, password="still definitely wrong"),
                _request(auth, settings, ip_address=ip_address),
                AuthAccountRepository(session),
            )
        assert blocked.value.status_code == 401
        assert blocked.value.detail == "invalid credentials"

    account_key, ip_key = auth.rate_limit_identifiers(email, ip_address)
    async with integration_database() as session:
        rows = (
            await session.scalars(
                select(AuthRateLimit).where(
                    AuthRateLimit.identifier_hash.in_([account_key[1], ip_key[1]])
                )
            )
        ).all()
    assert len(rows) == 2
    assert all(row.failure_count == 2 for row in rows)
    assert all(row.blocked_until is not None for row in rows)


async def test_api_key_usage_is_committed_separately_and_throttled(
    integration_database,
) -> None:
    auth = AuthService(private_key="", public_key="")
    auth.bind_database(integration_database, api_key_touch_interval_seconds=3600)
    raw_key, prefix, key_hash = auth.generate_api_key()
    key = ApiKey(name="QA key", prefix=prefix, key_hash=key_hash, scopes=["read"])
    async with integration_database() as session:
        session.add(key)
        await session.commit()
        key_id = key.id

    request = SimpleNamespace(headers={"x-api-key": raw_key}, cookies={})
    async with integration_database() as request_session:
        staged = await request_session.get(ApiKey, key_id)
        assert staged is not None
        staged.name = "must roll back"
        principal = await auth.authenticate(request, request_session)
        assert principal is not None and principal.kind == "api_key"

    async with integration_database() as session:
        persisted = await session.get(ApiKey, key_id)
        assert persisted is not None
        assert persisted.name == "QA key"
        assert persisted.last_used_at is not None
        first_used_at = persisted.last_used_at

    async with integration_database() as request_session:
        assert await auth.authenticate(request, request_session) is not None
    async with integration_database() as session:
        persisted = await session.get(ApiKey, key_id)
        assert persisted is not None
        assert persisted.last_used_at == first_used_at


async def test_concurrent_failed_attempt_updates_are_atomic(integration_database) -> None:
    identity = uuid.uuid4().hex * 2
    keys = (("account", identity), ("ip", identity[::-1]))
    moment = datetime.now(UTC)

    async def fail_once() -> None:
        async with integration_database() as session:
            accounts = AuthAccountRepository(session)
            await accounts.record_auth_failure(
                keys,
                moment=moment,
                attempt_limit=100,
                window=timedelta(minutes=15),
                base_cooldown=timedelta(seconds=2),
                max_cooldown=timedelta(minutes=15),
            )
            await accounts.commit()

    await asyncio.gather(*(fail_once() for _ in range(8)))
    async with integration_database() as session:
        rows = (
            await session.scalars(
                select(AuthRateLimit).where(
                    AuthRateLimit.identifier_hash.in_([value for _, value in keys])
                )
            )
        ).all()
    assert len(rows) == 2
    assert all(row.failure_count == 8 for row in rows)


async def test_successful_browser_login_does_not_store_raw_client_metadata(
    integration_database,
) -> None:
    identity = uuid.uuid4().hex
    email = f"session-{identity}@example.edu"
    password = "correct horse battery staple"
    auth = AuthService(private_key="", public_key="")
    settings = Settings()
    async with integration_database() as session:
        user = User(email=email, password_hash=auth.hash_password(password), role="editor")
        session.add(user)
        await session.commit()
        user_id = user.id

    request = cast(
        Request,
        SimpleNamespace(
            app=SimpleNamespace(state=SimpleNamespace(auth=auth, settings=settings)),
            headers={"user-agent": f"private-agent-{identity}"},
            client=SimpleNamespace(host="203.0.113.50"),
        ),
    )
    async with integration_database() as session:
        await login(LoginRequest(email=email, password=password), request, Response(), session)

    async with integration_database() as session:
        browser_session = await session.scalar(select(Session).where(Session.user_id == user_id))
        assert browser_session is not None
        assert browser_session.user_agent is None
        assert browser_session.ip_address is None


async def test_database_errors_hide_unique_bound_parameters() -> None:
    database = Database(get_test_settings().database_url)
    marker = f"news-secret-{uuid.uuid4().hex}"
    try:
        assert database.engine.sync_engine.hide_parameters
        async with database.session_factory() as session:
            with pytest.raises(DBAPIError) as raised:
                await session.execute(text("SELECT CAST(:value AS integer)"), {"value": marker})
        assert marker not in str(raised.value)
        assert "SQL parameters hidden" in str(raised.value)
    finally:
        await database.close()
