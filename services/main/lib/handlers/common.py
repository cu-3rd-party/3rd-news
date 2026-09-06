from __future__ import annotations

from datetime import UTC, datetime

from fastapi import HTTPException

from lib.core.service_factory import service_factory
from lib.infra.clients.auth.service import (
    Principal,
)
from lib.interactor.errors import ConflictError, NotFoundError


def now() -> datetime:
    return datetime.now(UTC)


def utc_timestamp(value: datetime) -> float:
    return (value if value.tzinfo else value.replace(tzinfo=UTC)).timestamp()


def error_status(error: Exception) -> HTTPException:
    if isinstance(error, NotFoundError):
        return HTTPException(404, str(error))
    if isinstance(error, ConflictError):
        return HTTPException(409, str(error))
    return HTTPException(422, str(error))


def actor(principal: Principal) -> str:
    return f"{principal.kind}:{principal.subject}"


async def news_dict(session, news, *, admin: bool = False) -> dict:
    return await service_factory.news_reader(session).serialize(news, admin=admin)


async def audit(session, principal, action, entity_type, entity_id, payload=None) -> None:
    service_factory.persistence(session).add_audit(
        actor=actor(principal),
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        payload=payload,
    )


async def request_news_projections(session, news_ids) -> None:
    await service_factory.persistence(session).request_news_projections(news_ids)
