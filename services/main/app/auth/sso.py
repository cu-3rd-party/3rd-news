"""Placeholder for the campus identity provider.

The shape of the university SSO is not known yet, so this backend only shows
where it plugs in. Fill in `authenticate`, add `"sso"` to `NEWS_AUTH_BACKENDS`,
and no endpoint changes.

Typical implementations:

* **Trusted header** — a reverse proxy (Keycloak gatekeeper, oauth2-proxy)
  authenticates and forwards `X-Forwarded-User`. Read the header, map it onto a
  `User` row via `sso_subject`, done. Only safe when the proxy is the sole
  route to this service.
* **OIDC ID token** — the caller sends the provider's JWT; verify it against
  the provider's JWKS. Mostly `JwtBackend` with a different key source.
* **CAS / SAML** — redirect flow, then hand out a normal session cookie; that
  makes it a login route rather than a backend.
"""

from __future__ import annotations

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from .base import AuthBackend, Principal


class SsoBackend(AuthBackend):
    name = "sso"

    async def authenticate(self, request: Request, session: AsyncSession) -> Principal | None:
        return None
