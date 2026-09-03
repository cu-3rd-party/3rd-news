"""FastAPI dependencies shared by the routers."""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Annotated, Any

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import Principal, authenticate
from .db import get_session

DbSession = Annotated[AsyncSession, Depends(get_session)]


async def current_principal(request: Request, session: DbSession) -> Principal:
    principal = await authenticate(request, session)
    if principal is None:
        raise HTTPException(
            status_code=401,
            detail="authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    # Backends may touch rows (last_used_at); persist that without a router.
    await session.commit()
    return principal


CurrentPrincipal = Annotated[Principal, Depends(current_principal)]


def require_scope(*scopes: str) -> Callable[..., Coroutine[Any, Any, Principal]]:
    """Dependency factory: caller must hold at least one of `scopes`."""

    async def dependency(principal: CurrentPrincipal) -> Principal:
        if not any(principal.has_scope(scope) for scope in scopes):
            raise HTTPException(
                status_code=403,
                detail=f"requires one of scopes: {', '.join(scopes)}",
            )
        return principal

    return dependency


require_read = require_scope("read")
require_ingest = require_scope("ingest")
require_admin = require_scope("admin")
require_editor = require_scope("editor", "admin")

ReadPrincipal = Annotated[Principal, Depends(require_read)]
IngestPrincipal = Annotated[Principal, Depends(require_ingest)]
AdminPrincipal = Annotated[Principal, Depends(require_admin)]
EditorPrincipal = Annotated[Principal, Depends(require_editor)]
