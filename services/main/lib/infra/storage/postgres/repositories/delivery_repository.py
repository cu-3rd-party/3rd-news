from datetime import UTC, datetime, timedelta
from uuid import UUID

from lib.infra.storage.postgres.models import AuditLog, OutboxEvent
from lib.interactor.errors import NotFoundError
from lib.interactor.interfaces.storage.delivery import DeliveryStorage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class DeliveryRepository(DeliveryStorage):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def pending(self, limit: int) -> list[dict[str, object]]:
        events = await self.session.scalars(
            select(OutboxEvent)
            .where(OutboxEvent.delivered_at.is_(None))
            .order_by(OutboxEvent.created_at)
            .limit(limit)
        )
        return [
            {
                "id": str(event.id),
                "topic": event.topic,
                "attempts": event.attempts,
                "available_at": event.available_at,
                "error_code": event.last_error,
                "status": "quarantined"
                if (event.last_error or "").startswith("permanent:")
                else "retrying"
                if event.attempts
                else "pending",
            }
            for event in events
        ]

    async def replay(self, event_id: UUID, *, actor: str, delay_seconds: int) -> datetime:
        event = await self.session.get(OutboxEvent, event_id, with_for_update=True)
        if event is None:
            raise NotFoundError("event not found")

        event.available_at = datetime.now(UTC) + timedelta(seconds=delay_seconds)
        event.delivered_at = None
        event.attempts = 0
        event.lease_until = None
        event.owner = None
        event.last_error = None
        self.session.add(
            AuditLog(
                actor=actor,
                action="delivery.replay",
                entity_type="outbox",
                entity_id=str(event_id),
                payload={"delay_seconds": delay_seconds},
            )
        )
        await self.session.commit()
        return event.available_at
