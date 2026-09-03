"""Pluggable authentication for the client-facing endpoints.

The delivery endpoint must eventually accept tokens, JWTs and campus SSO, and
nobody knows yet what the SSO will look like. So authentication is a *chain of
backends*: each one looks at the request and either produces a `Principal` or
steps aside. Adding a scheme later means adding one class and one line of
config (`NEWS_AUTH_BACKENDS`), never touching the endpoints.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(slots=True)
class Principal:
    """Whoever is making the request, normalised across auth schemes."""

    #: Which backend authenticated this request ("api_key", "jwt", ...).
    kind: str
    #: Stable identifier, for logs and audit entries.
    subject: str
    display_name: str = ""
    scopes: set[str] = field(default_factory=set)
    #: Set when the principal maps onto an admin user.
    user_id: str | None = None
    role: str | None = None
    #: Server-side filters silently ANDed into every delivery query. Lets a key
    #: be scoped to, say, one faculty without trusting the caller's parameters.
    filter_preset: dict = field(default_factory=dict)

    def has_scope(self, scope: str) -> bool:
        return scope in self.scopes or "admin" in self.scopes


class AuthBackend(abc.ABC):
    """One way of proving who you are."""

    #: Value used in `NEWS_AUTH_BACKENDS`.
    name: str

    @abc.abstractmethod
    async def authenticate(self, request: Request, session: AsyncSession) -> Principal | None:
        """Return a principal, or None when this backend does not apply.

        Raise `fastapi.HTTPException` only when the caller *did* present a
        credential of this kind and it was invalid — a missing credential must
        return None so the next backend gets its turn.
        """
