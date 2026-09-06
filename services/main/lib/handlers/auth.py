from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, HTTPException, Request, Response

from lib.core.config import (
    AUTH_CSRF_COOKIE,
    AUTH_DUMMY_PASSWORD_HASH,
    AUTH_ROLE_SCOPES,
    AUTH_SESSION_COOKIE,
)
from lib.core.service_factory import service_factory
from lib.dto.principal import Principal
from lib.dto.requests import (
    LoginRequest,
    TokenResponse,
)
from lib.interactor.errors.password_verification_capacity import (
    PasswordVerificationCapacityError,
)
from lib.interactor.interfaces.storage.auth_account import AuthAccountStorage

from .common import now
from .dependencies import DbSession, ReadPrincipal

router = APIRouter()


async def _authenticated_user(
    payload: LoginRequest,
    request: Request,
    accounts: AuthAccountStorage,
):
    auth = request.app.state.auth
    moment = now()
    rate_keys = auth.rate_limit_identifiers(payload.email, auth.client_ip(request))
    if await accounts.auth_rate_limited(rate_keys, moment):
        raise HTTPException(401, "invalid credentials")

    user = await accounts.find_user_by_email(payload.email)
    encoded = (
        user.password_hash if user is not None and user.is_active else AUTH_DUMMY_PASSWORD_HASH
    )
    try:
        password_valid = await auth.verify_password_bounded(payload.password, encoded)
    except PasswordVerificationCapacityError:
        raise HTTPException(503, "authentication temporarily unavailable") from None
    if user is None or not user.is_active or not password_valid:
        settings = request.app.state.settings
        await accounts.record_auth_failure(
            rate_keys,
            moment=moment,
            attempt_limit=settings.auth_login_attempt_limit,
            window=timedelta(seconds=settings.auth_login_window_seconds),
            base_cooldown=timedelta(seconds=settings.auth_login_base_cooldown_seconds),
            max_cooldown=timedelta(seconds=settings.auth_login_max_cooldown_seconds),
        )
        await accounts.commit()
        raise HTTPException(401, "invalid credentials")

    await accounts.clear_account_auth_failures(rate_keys[0][1])
    return user


@router.post("/api/v1/auth/login")
async def login(
    payload: LoginRequest, request: Request, response: Response, session: DbSession
) -> dict:
    accounts = service_factory.auth_account(session)
    user = await _authenticated_user(payload, request, accounts)
    auth = request.app.state.auth
    token, token_hash, csrf, csrf_hash = auth.generate_session()
    await accounts.create_session(
        user_id=user.id,
        token_hash=token_hash,
        csrf_hash=csrf_hash,
        expires_at=now() + timedelta(hours=8),
    )
    user.last_login_at = now()
    await accounts.commit()
    secure = request.app.state.settings.environment == "production"
    response.set_cookie(
        AUTH_SESSION_COOKIE,
        token,
        httponly=True,
        secure=secure,
        samesite="lax",
        max_age=28800,
        path="/",
    )
    response.set_cookie(
        AUTH_CSRF_COOKIE,
        csrf,
        httponly=False,
        secure=secure,
        samesite="lax",
        max_age=28800,
        path="/",
    )
    return {
        "kind": "session",
        "subject": user.email,
        "display_name": user.full_name or user.email,
        "role": user.role,
    }


@router.post("/api/v1/auth/token", response_model=TokenResponse)
async def token(payload: LoginRequest, request: Request, session: DbSession) -> TokenResponse:
    accounts = service_factory.auth_account(session)
    user = await _authenticated_user(payload, request, accounts)
    auth = request.app.state.auth
    principal = Principal(
        "user",
        user.email,
        user.full_name or user.email,
        AUTH_ROLE_SCOPES.get(user.role, frozenset({"read"})),
        user.id,
        role=user.role,
    )
    value, expires = auth.issue_token(principal)
    user.last_login_at = now()
    await accounts.commit()
    return TokenResponse(access_token=value, expires_in=expires)


@router.post("/api/v1/auth/logout", status_code=204)
async def logout(request: Request, response: Response, session: DbSession) -> Response:
    raw = request.cookies.get(AUTH_SESSION_COOKIE)
    if raw:
        accounts = service_factory.auth_account(session)
        row = await accounts.find_session_by_hash(request.app.state.auth.hash_secret(raw))
        if row:
            if not request.app.state.auth.valid_csrf(request, row):
                raise HTTPException(403, "CSRF validation failed")
            row.revoked_at = now()
            await accounts.commit()
    response.delete_cookie(AUTH_SESSION_COOKIE, path="/")
    response.delete_cookie(AUTH_CSRF_COOKIE, path="/")
    response.status_code = 204
    return response


@router.get("/api/v1/auth/me")
async def me(principal: ReadPrincipal) -> dict:
    return {
        "kind": principal.kind,
        "subject": principal.subject,
        "display_name": principal.display_name,
        "scopes": sorted(principal.scopes),
        "role": principal.role,
    }
