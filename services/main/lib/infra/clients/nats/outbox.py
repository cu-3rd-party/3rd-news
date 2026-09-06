from __future__ import annotations

import asyncio
import logging
import math
import re
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

from lib.core.config import (
    OUTBOX_ATTEMPT_COUNTER_MAX,
    OUTBOX_RETRY_DELAY_MAX_SECONDS,
    OUTBOX_RETRY_EXPONENT_MAX,
)
from lib.infra.storage.postgres.models import OutboxEvent
from lib.interactor.interfaces.clients.outbox import OutboxClient
from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .jetstream import JetStreamBroker

_TOPIC = re.compile(r"^[a-z][a-z0-9_.-]{0,118}[a-z0-9]$")
_SENSITIVE_KEYS = frozenset(
    {"body", "body_md", "text", "raw", "raw_payload", "request", "response", "token", "secret"}
)


class OutboxPublisher(OutboxClient):
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        broker: JetStreamBroker,
        *,
        owner: str,
        subject_prefix: str = "thirdnews.v2",
        batch_size: int = 20,
        lease_seconds: int = 120,
        poll_seconds: float = 0.5,
    ) -> None:
        self._sessions = session_factory
        self._broker = broker
        self._owner = owner
        self._prefix = subject_prefix.rstrip(".")
        self._batch_size = batch_size
        self._lease_seconds = lease_seconds
        self._poll_seconds = poll_seconds

    async def run(self, *, stop: asyncio.Event) -> None:
        while not stop.is_set():
            claimed = await self.publish_batch()
            if claimed:
                continue
            try:
                await asyncio.wait_for(stop.wait(), timeout=self._poll_seconds)
            except TimeoutError:
                pass

    async def publish_batch(self) -> int:
        event_ids = await self._claim()
        for event_id in event_ids:
            await self._publish_one(event_id)
        return len(event_ids)

    async def _claim(self) -> list[uuid.UUID]:
        now = datetime.now(UTC)
        lease_until = now + timedelta(seconds=self._lease_seconds)
        async with self._sessions() as session, session.begin():
            rows = (
                await session.scalars(
                    select(OutboxEvent)
                    .where(
                        OutboxEvent.delivered_at.is_(None),
                        OutboxEvent.available_at <= now,
                        or_(
                            OutboxEvent.last_error.is_(None),
                            ~OutboxEvent.last_error.startswith("permanent:"),
                        ),
                        or_(OutboxEvent.lease_until.is_(None), OutboxEvent.lease_until < now),
                    )
                    .order_by(OutboxEvent.created_at, OutboxEvent.id)
                    .limit(self._batch_size)
                    .with_for_update(skip_locked=True)
                )
            ).all()
            for row in rows:
                row.owner = self._owner
                row.lease_until = lease_until
                row.attempts = min(row.attempts + 1, OUTBOX_ATTEMPT_COUNTER_MAX)
            return [row.id for row in rows]

    async def _publish_one(self, event_id: uuid.UUID) -> None:
        async with self._sessions() as session:
            event = await session.get(OutboxEvent, event_id)
            if event is None or event.owner != self._owner or event.delivered_at is not None:
                return
            topic = event.topic
            payload = dict(event.payload)
            aggregate_id = str(event.aggregate_id) if event.aggregate_id else ""
            attempts = event.attempts
            occurred_at = event.created_at
        try:
            self._validate_event(topic, payload)
            envelope = {
                "contract_version": "2.0",
                "event_id": str(event_id),
                "event_type": topic,
                "occurred_at": occurred_at.isoformat(),
                "aggregate_id": aggregate_id,
                "aggregate_version": int(payload.get("revision") or 1),
                "metadata": {"correlation_id": str(event_id)},
                "payload": payload,
            }
            subject_topic = topic.removesuffix(".v2")
        except (TypeError, ValueError) as exc:
            await self._mark_failed(event_id, attempts, exc, permanent=True)
            return
        try:
            await self._broker.publish_json(
                f"{self._prefix}.{subject_topic}",
                envelope,
                message_id=str(event_id),
                headers={"X-Aggregate-Id": aggregate_id, "X-Event-Id": str(event_id)},
            )
        except Exception as exc:
            await self._mark_failed(event_id, attempts, exc, permanent=False)
            return
        now = datetime.now(UTC)
        async with self._sessions() as session, session.begin():
            await session.execute(
                update(OutboxEvent)
                .where(
                    OutboxEvent.id == event_id,
                    OutboxEvent.owner == self._owner,
                    OutboxEvent.delivered_at.is_(None),
                )
                .values(delivered_at=now, lease_until=None, owner=None, last_error=None)
            )

    async def _mark_failed(
        self,
        event_id: uuid.UUID,
        attempts: int,
        error: Exception,
        *,
        permanent: bool,
    ) -> None:
        delay = min(2 ** min(attempts, OUTBOX_RETRY_EXPONENT_MAX), OUTBOX_RETRY_DELAY_MAX_SECONDS)
        error_code = ("permanent:" if permanent else "") + type(error).__name__
        logging.getLogger(__name__).warning(
            "outbox event %s %s (%s)",
            event_id,
            "quarantined" if permanent else "scheduled for retry",
            type(error).__name__,
        )
        async with self._sessions() as session, session.begin():
            await session.execute(
                update(OutboxEvent)
                .where(
                    OutboxEvent.id == event_id,
                    OutboxEvent.owner == self._owner,
                    OutboxEvent.delivered_at.is_(None),
                )
                .values(
                    owner=None,
                    lease_until=None,
                    available_at=datetime.now(UTC) + timedelta(seconds=delay),
                    last_error=error_code,
                )
            )

    @staticmethod
    def _validate_event(topic: str, payload: Mapping[str, Any]) -> None:
        if not _TOPIC.fullmatch(topic):
            raise ValueError("invalid outbox topic")

        def inspect(value: Any, path: tuple[str, ...] = ()) -> None:
            if isinstance(value, Mapping):
                for key, nested in value.items():
                    normalized = str(key).lower()
                    if normalized in _SENSITIVE_KEYS:
                        raise ValueError(
                            f"sensitive payload field is forbidden: {'.'.join((*path, normalized))}"
                        )
                    inspect(nested, (*path, normalized))
            elif isinstance(value, list):
                for nested in value:
                    inspect(nested, path)
            elif value is not None and not isinstance(value, (str, int, float, bool)):
                raise ValueError("outbox payload is not JSON scalar data")
            elif isinstance(value, float) and not math.isfinite(value):
                raise ValueError("outbox payload contains a non-finite number")

        inspect(payload)
