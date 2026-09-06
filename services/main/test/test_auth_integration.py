from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from lib.infra.clients.auth import AuthService, Principal
from lib.infra.storage.postgres.models import User

pytestmark = pytest.mark.integration


def auth_service() -> AuthService:
    private = Ed25519PrivateKey.generate()
    private_pem = private.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    public_pem = (
        private.public_key()
        .public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )
    return AuthService(private_key=private_pem, public_key=public_pem)


async def test_bearer_token_is_rejected_after_user_is_deactivated(integration_database) -> None:
    auth = auth_service()
    user = User(
        email=f"qa-disabled-{uuid.uuid4()}@example.test",
        full_name="Disabled QA User",
        role="admin",
        is_active=False,
    )
    async with integration_database() as session:
        session.add(user)
        await session.commit()
        user_id = user.id

    token, _ = auth.issue_token(
        Principal(
            "user",
            user.email,
            user.full_name or user.email,
            frozenset({"read", "admin"}),
            user_id=user_id,
            role="admin",
        )
    )
    request = SimpleNamespace(headers={"authorization": f"Bearer {token}"}, cookies={})
    async with integration_database() as session:
        assert await auth.authenticate(request, session) is None


async def test_bearer_scopes_follow_current_database_role(integration_database) -> None:
    auth = auth_service()
    user = User(
        email=f"qa-demoted-{uuid.uuid4()}@example.test",
        full_name="Demoted QA User",
        role="editor",
        is_active=True,
    )
    async with integration_database() as session:
        session.add(user)
        await session.commit()
        user_id = user.id

    stale_admin_token, _ = auth.issue_token(
        Principal(
            "user",
            user.email,
            user.full_name or user.email,
            frozenset({"read", "ingest", "editor", "admin", "raw_audit"}),
            user_id=user_id,
            role="admin",
        )
    )
    request = SimpleNamespace(
        headers={"authorization": f"Bearer {stale_admin_token}"},
        cookies={},
    )
    async with integration_database() as session:
        current = await auth.authenticate(request, session)

    assert current is not None
    assert current.role == "editor"
    assert current.scopes == frozenset({"read", "editor"})
