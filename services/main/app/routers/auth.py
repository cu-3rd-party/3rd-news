"""Login, logout, token issuing, and "who am I".

Three ways in, all landing on the same `Principal`:

* `POST /login` — email + password, sets the session cookie (admin SPA).
* `POST /token` — email + password, returns a JWT (scripts, mobile clients).
* An API key issued in the admin, sent as `X-API-Key` on every request.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Request, Response
from sqlalchemy import select

from ..auth import ROLE_SCOPES
from ..config import settings
from ..deps import CurrentPrincipal, DbSession
from ..models import Session as SessionRow
from ..models import User
from ..schemas import LoginRequest, MeResponse, TokenResponse
from ..security import generate_session_token, hash_secret, issue_jwt, verify_password

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


async def _authenticate_user(session, payload: LoginRequest) -> User:
    user = (
        await session.execute(select(User).where(User.email == payload.email.lower()))
    ).scalar_one_or_none()
    if user is None or not user.is_active or not verify_password(payload.password, user.password_hash):
        # Same message either way: do not leak which addresses exist.
        raise HTTPException(status_code=401, detail="invalid credentials")
    user.last_login_at = datetime.now(timezone.utc)
    return user


@router.post("/login", response_model=MeResponse, summary="Log in and set a session cookie")
async def login(
    payload: LoginRequest, request: Request, response: Response, session: DbSession
) -> MeResponse:
    user = await _authenticate_user(session, payload)

    token, token_hash = generate_session_token()
    session.add(
        SessionRow(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=datetime.now(timezone.utc)
            + timedelta(seconds=settings.session_ttl_seconds),
            user_agent=request.headers.get("user-agent", "")[:400],
            ip=request.client.host if request.client else None,
        )
    )
    await session.commit()

    response.set_cookie(
        settings.session_cookie_name,
        token,
        max_age=settings.session_ttl_seconds,
        httponly=True,
        samesite="lax",
        secure=settings.environment == "production",
        path="/",
    )
    scopes = sorted(ROLE_SCOPES.get(user.role, {"read"}))
    return MeResponse(
        kind="session",
        subject=user.email,
        display_name=user.full_name or user.email,
        scopes=scopes,
        role=user.role,
    )


@router.post("/token", response_model=TokenResponse, summary="Exchange credentials for a JWT")
async def issue_token(payload: LoginRequest, session: DbSession) -> TokenResponse:
    user = await _authenticate_user(session, payload)
    await session.commit()
    scopes = sorted(ROLE_SCOPES.get(user.role, {"read"}))
    token, expires_in = issue_jwt(
        user.email, scopes, extra={"user_id": str(user.id), "role": user.role}
    )
    return TokenResponse(access_token=token, expires_in=expires_in)


@router.post("/logout", status_code=204, summary="Revoke the current session cookie")
async def logout(request: Request, response: Response, session: DbSession) -> Response:
    token = request.cookies.get(settings.session_cookie_name)
    if token:
        row = (
            await session.execute(
                select(SessionRow).where(SessionRow.token_hash == hash_secret(token))
            )
        ).scalar_one_or_none()
        if row is not None:
            row.revoked_at = datetime.now(timezone.utc)
            await session.commit()
    response.delete_cookie(settings.session_cookie_name, path="/")
    response.status_code = 204
    return response


@router.get("/me", response_model=MeResponse, summary="Describe the current credential")
async def me(principal: CurrentPrincipal) -> MeResponse:
    return MeResponse(
        kind=principal.kind,
        subject=principal.subject,
        display_name=principal.display_name,
        scopes=sorted(principal.scopes),
        role=principal.role,
    )
