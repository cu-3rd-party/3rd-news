from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import ApiKey
from ..security import API_KEY_PREFIX, hash_secret
from .base import AuthBackend, Principal


def _extract(request: Request) -> str | None:
    header = request.headers.get("X-API-Key")
    if header:
        return header.strip()
    authorization = request.headers.get("Authorization", "")
    if authorization.lower().startswith("apikey "):
        return authorization[7:].strip()
    # Convenience for <img>/<iframe> style consumers that cannot set headers.
    return request.query_params.get("api_key")


class ApiKeyBackend(AuthBackend):
    name = "api_key"

    async def authenticate(self, request: Request, session: AsyncSession) -> Principal | None:
        raw = _extract(request)
        if not raw or not raw.startswith(API_KEY_PREFIX):
            return None

        key = (
            await session.execute(
                select(ApiKey).where(ApiKey.key_hash == hash_secret(raw))
            )
        ).scalar_one_or_none()
        if key is None or not key.is_active:
            raise HTTPException(status_code=401, detail="invalid api key")
        now = datetime.now(timezone.utc)
        if key.expires_at and key.expires_at <= now:
            raise HTTPException(status_code=401, detail="api key expired")

        key.last_used_at = now
        return Principal(
            kind=self.name,
            subject=str(key.id),
            display_name=key.name,
            scopes=set(key.scopes or []),
            filter_preset=key.filter_preset or {},
        )
