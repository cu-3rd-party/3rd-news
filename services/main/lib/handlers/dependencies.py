from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import Annotated, Any

from fastapi import Depends, HTTPException, Request

from lib.core.service_factory import service_factory
from lib.infra.clients.auth import Principal
from lib.infra.clients.auth.service import SESSION_COOKIE


async def session(request: Request) -> AsyncIterator[Any]:
    async with request.app.state.database.session_factory() as value:
        yield value


DbSession = Annotated[Any, Depends(session)]


async def principal(request: Request, session: DbSession) -> Principal:
    value = await request.app.state.auth.authenticate(request, session)
    if value is None:
        raise HTTPException(401, "authentication required", headers={"WWW-Authenticate": "Bearer"})
    return value


CurrentPrincipal = Annotated[Principal, Depends(principal)]


def require(*scopes: str) -> Callable:
    async def dependency(
        request: Request,
        value: CurrentPrincipal,
        session: DbSession,
    ) -> Principal:
        if not value.allows(*scopes):
            raise HTTPException(403, f"requires one of scopes: {', '.join(scopes)}")
        if request.method not in {"GET", "HEAD", "OPTIONS"} and value.kind == "session":
            csrf = request.headers.get("x-csrf-token", "")
            if not csrf or csrf != request.cookies.get("thirdnews_csrf"):
                raise HTTPException(403, "CSRF validation failed")
            raw_session = request.cookies.get(SESSION_COOKIE, "")
            row = await service_factory.auth_account(session).find_session_by_hash(
                request.app.state.auth.hash_secret(raw_session)
            )
            if row is None or not request.app.state.auth.valid_csrf(request, row):
                raise HTTPException(403, "CSRF validation failed")
        return value

    return dependency


ReadPrincipal = Annotated[Principal, Depends(require("read"))]
IngestPrincipal = Annotated[Principal, Depends(require("ingest"))]
EditorPrincipal = Annotated[Principal, Depends(require("editor", "admin"))]
AdminPrincipal = Annotated[Principal, Depends(require("admin"))]
