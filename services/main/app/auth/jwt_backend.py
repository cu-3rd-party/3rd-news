from __future__ import annotations

import jwt
from fastapi import HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ..security import decode_jwt
from .base import AuthBackend, Principal


class JwtBackend(AuthBackend):
    """`Authorization: Bearer <jwt>`.

    Verifies tokens this service issued (HS256 with the app secret) and, when
    `NEWS_JWT_PUBLIC_KEY` is configured, tokens minted by an external issuer.
    """

    name = "jwt"

    async def authenticate(self, request: Request, session: AsyncSession) -> Principal | None:
        authorization = request.headers.get("Authorization", "")
        if not authorization.lower().startswith("bearer "):
            return None
        token = authorization[7:].strip()
        try:
            claims = decode_jwt(token)
        except jwt.PyJWTError as exc:
            raise HTTPException(status_code=401, detail=f"invalid token: {exc}") from exc

        scope_claim = claims.get("scope") or claims.get("scopes") or "read"
        scopes = set(scope_claim.split()) if isinstance(scope_claim, str) else set(scope_claim)
        return Principal(
            kind=self.name,
            subject=str(claims.get("sub", "anonymous")),
            display_name=str(claims.get("name") or claims.get("sub") or ""),
            scopes=scopes,
            user_id=claims.get("user_id"),
            role=claims.get("role"),
            filter_preset=claims.get("filter_preset") or {},
        )
