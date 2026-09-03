from __future__ import annotations

from datetime import datetime, timezone

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.orm import joinedload
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..models import Session as SessionRow
from ..security import hash_secret
from .base import AuthBackend, Principal

#: Admins get every read scope implicitly; editors get read + write on news.
ROLE_SCOPES = {
    "admin": {"read", "ingest", "admin"},
    "editor": {"read", "editor"},
    "reader": {"read"},
}


class SessionCookieBackend(AuthBackend):
    """The admin SPA's cookie, and any browser client logged in the same way."""

    name = "session"

    async def authenticate(self, request: Request, session: AsyncSession) -> Principal | None:
        token = request.cookies.get(settings.session_cookie_name)
        if not token:
            return None

        row = (
            await session.execute(
                select(SessionRow)
                .options(joinedload(SessionRow.user))
                .where(SessionRow.token_hash == hash_secret(token))
            )
        ).scalar_one_or_none()
        now = datetime.now(timezone.utc)
        if row is None or row.revoked_at is not None or row.expires_at <= now:
            # A stale cookie should not lock the caller out of other schemes.
            return None
        user = row.user
        if user is None or not user.is_active:
            return None

        return Principal(
            kind=self.name,
            subject=user.email,
            display_name=user.full_name or user.email,
            scopes=set(ROLE_SCOPES.get(user.role, {"read"})),
            user_id=str(user.id),
            role=user.role,
        )
