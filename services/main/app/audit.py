"""Append-only record of who changed what in the admin."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from .auth import Principal
from .models import AuditLog


async def log(
    session: AsyncSession,
    principal: Principal,
    action: str,
    entity: str,
    entity_id: str | None = None,
    payload: dict | None = None,
) -> None:
    session.add(
        AuditLog(
            actor=f"{principal.kind}:{principal.subject}",
            action=action,
            entity=entity,
            entity_id=entity_id,
            payload=payload or {},
        )
    )
