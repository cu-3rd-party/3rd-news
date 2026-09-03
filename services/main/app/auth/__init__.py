"""Auth backend registry.

`NEWS_AUTH_BACKENDS` lists the backends to try, in order. Unknown names raise
at import time rather than silently disabling a scheme.
"""

from __future__ import annotations

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from .api_key import ApiKeyBackend
from .base import AuthBackend, Principal
from .jwt_backend import JwtBackend
from .session_backend import ROLE_SCOPES, SessionCookieBackend
from .sso import SsoBackend

REGISTRY: dict[str, type[AuthBackend]] = {
    ApiKeyBackend.name: ApiKeyBackend,
    JwtBackend.name: JwtBackend,
    SessionCookieBackend.name: SessionCookieBackend,
    SsoBackend.name: SsoBackend,
}


def build_chain() -> list[AuthBackend]:
    chain: list[AuthBackend] = []
    for name in settings.auth_backends:
        try:
            chain.append(REGISTRY[name]())
        except KeyError as exc:
            known = ", ".join(sorted(REGISTRY))
            raise RuntimeError(f"unknown auth backend {name!r}; known: {known}") from exc
    return chain


_chain = build_chain()


async def authenticate(request: Request, session: AsyncSession) -> Principal | None:
    for backend in _chain:
        principal = await backend.authenticate(request, session)
        if principal is not None:
            return principal
    return None


__all__ = [
    "AuthBackend",
    "Principal",
    "REGISTRY",
    "ROLE_SCOPES",
    "authenticate",
    "build_chain",
]
