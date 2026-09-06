from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import pytest
from lib.core.workers import _release_referenced_job
from lib.infra.clients.nats import DatabaseInboxHandler, OutboxPublisher
from lib.infra.clients.nats.consumer import IncomingMessage
from lib.infra.storage.postgres.models import (
    InboxMessage,
    News,
    OutboxEvent,
    SearchProjection,
    Setting,
)
from sqlalchemy import delete, update

pytestmark = pytest.mark.integration


class RecordingBroker:
    def __init__(self, *, failure: Exception | None = None) -> None:
        self.failure = failure
        self.calls: list[tuple[str, dict, str, dict[str, str]]] = []

    async def publish_json(self, subject, payload, *, message_id, headers) -> None:
        self.calls.append((subject, dict(payload), message_id, dict(headers)))
        if self.failure is not None:
            raise self.failure


async def test_inbox_rolls_back_marker_and_side_effect_before_redelivery(
    integration_database,
) -> None:
    message_id = f"inbox-{uuid.uuid4()}"
    setting_key = f"qa-{uuid.uuid4()}"

    async def fails_after_write(session, payload) -> None:
        session.add(Setting(key=setting_key, value={"event": payload["event"]}))
        await session.flush()
        raise RuntimeError("simulated crash before commit")

    message = IncomingMessage(
        id=message_id,
        subject="thirdnews.v2.qa",
        payload={"event": "first"},
        deliveries=1,
    )
    failing_handler = DatabaseInboxHandler(
        integration_database,
        consumer_name="qa-atomic-inbox",
        callback=fails_after_write,
    )
    with pytest.raises(RuntimeError, match="simulated crash"):
        await failing_handler(message)

    async with integration_database() as session:
        assert await session.get(Setting, setting_key) is None
        assert await session.get(InboxMessage, ("qa-atomic-inbox", message_id)) is None

    calls = 0

    async def succeeds(session, payload) -> None:
        nonlocal calls
        calls += 1
        session.add(Setting(key=setting_key, value={"event": payload["event"]}))

    handler = DatabaseInboxHandler(
        integration_database,
        consumer_name="qa-atomic-inbox",
        callback=succeeds,
    )
    await handler(message)
    await handler(message)

    async with integration_database() as session:
        marker = await session.get(InboxMessage, ("qa-atomic-inbox", message_id))
        assert marker is not None and marker.processed_at is not None
        assert (await session.get(Setting, setting_key)).value == {"event": "first"}
    assert calls == 1


async def test_concurrent_inbox_delivery_applies_callback_once(integration_database) -> None:
    message_id = f"concurrent-{uuid.uuid4()}"
    setting_key = f"qa-{uuid.uuid4()}"
    entered = asyncio.Event()
    release = asyncio.Event()
    calls = 0

    async def callback(session, payload) -> None:
        nonlocal calls
        calls += 1
        entered.set()
        await release.wait()
        session.add(Setting(key=setting_key, value=dict(payload)))

    handler = DatabaseInboxHandler(
        integration_database,
        consumer_name="qa-concurrent-inbox",
        callback=callback,
    )
    message = IncomingMessage(
        id=message_id,
        subject="thirdnews.v2.qa",
        payload={"delivery": "once"},
        deliveries=1,
    )
    first = asyncio.create_task(handler(message))
    await asyncio.wait_for(entered.wait(), timeout=2)
    second = asyncio.create_task(handler(message))
    release.set()
    await asyncio.wait_for(asyncio.gather(first, second), timeout=5)

    assert calls == 1
    async with integration_database() as session:
        marker = await session.get(InboxMessage, ("qa-concurrent-inbox", message_id))
        assert marker is not None and marker.processed_at is not None


async def test_two_outbox_publishers_cannot_publish_same_live_lease(
    integration_database,
) -> None:
    async with integration_database() as session, session.begin():
        await session.execute(delete(OutboxEvent).where(OutboxEvent.topic.like("qa.%")))
    event = OutboxEvent(
        topic="qa.delivery.v2",
        aggregate_id=uuid.uuid4(),
        payload={"aggregate_id": str(uuid.uuid4()), "revision": 1},
        created_at=datetime(2000, 1, 1, tzinfo=UTC),
        available_at=datetime(2000, 1, 1, tzinfo=UTC),
    )
    async with integration_database() as session:
        session.add(event)
        await session.commit()
        event_id = event.id

    left_broker = RecordingBroker()
    right_broker = RecordingBroker()
    left = OutboxPublisher(
        integration_database, cast(Any, left_broker), owner="qa-left", batch_size=1
    )
    right = OutboxPublisher(
        integration_database, cast(Any, right_broker), owner="qa-right", batch_size=1
    )
    await asyncio.gather(left.publish_batch(), right.publish_batch())

    matching_calls = [
        call for call in left_broker.calls + right_broker.calls if call[2] == str(event_id)
    ]
    assert len(matching_calls) == 1
    async with integration_database() as session:
        stored = await session.get(OutboxEvent, event_id)
        assert stored is not None
        assert stored.delivered_at is not None
        assert stored.owner is None and stored.lease_until is None
        assert stored.attempts == 1


async def test_failed_outbox_publish_is_recoverable_by_another_owner(
    integration_database,
) -> None:
    async with integration_database() as session, session.begin():
        await session.execute(delete(OutboxEvent).where(OutboxEvent.topic.like("qa.%")))
    event = OutboxEvent(
        topic="qa.redelivery.v2",
        aggregate_id=uuid.uuid4(),
        payload={"aggregate_id": str(uuid.uuid4())},
        created_at=datetime(2000, 1, 1, tzinfo=UTC),
        available_at=datetime(2000, 1, 1, tzinfo=UTC),
    )
    async with integration_database() as session:
        session.add(event)
        await session.commit()
        event_id = event.id

    failing_broker = RecordingBroker(failure=ConnectionError("broker unavailable"))
    first = OutboxPublisher(
        integration_database, cast(Any, failing_broker), owner="qa-crashed", batch_size=1
    )
    assert await first.publish_batch() == 1

    async with integration_database() as session, session.begin():
        stored = await session.get(OutboxEvent, event_id)
        assert stored is not None
        assert stored.delivered_at is None
        assert stored.owner is None and stored.lease_until is None
        assert stored.attempts == 1
        assert "ConnectionError" in (stored.last_error or "")
        await session.execute(
            update(OutboxEvent)
            .where(OutboxEvent.id == event_id)
            .values(available_at=datetime.now(UTC) - timedelta(seconds=1))
        )

    recovered_broker = RecordingBroker()
    second = OutboxPublisher(
        integration_database, cast(Any, recovered_broker), owner="qa-recovery", batch_size=1
    )
    assert await second.publish_batch() == 1
    assert len(recovered_broker.calls) == 1
    async with integration_database() as session:
        stored = await session.get(OutboxEvent, event_id)
        assert stored is not None and stored.delivered_at is not None
        assert stored.attempts == 2


async def test_search_event_creates_fresh_projection_and_preserves_high_water_mark(
    integration_database,
) -> None:
    async with integration_database() as session, session.begin():
        news = News(revision=7, visibility_revision=7)
        session.add(news)
        await session.flush()
        news_id = news.id
        await _release_referenced_job(
            session,
            {"payload": {"news_id": str(news_id), "revision": 6}},
        )

    async with integration_database() as session:
        projection = await session.get(SearchProjection, news_id)
        assert projection is not None
        assert projection.desired_revision == 7
        assert projection.status == "pending"

    async with integration_database() as session, session.begin():
        await _release_referenced_job(
            session,
            {"payload": {"news_id": str(news_id), "revision": 5}},
        )

    async with integration_database() as session:
        projection = await session.get(SearchProjection, news_id)
        assert projection is not None and projection.desired_revision == 7


async def test_outbox_recovers_automatically_after_more_than_old_retry_budget(integration_database):
    event = OutboxEvent(
        topic="qa.outage.v2",
        payload={"revision": 1},
        created_at=datetime(1999, 1, 1, tzinfo=UTC),
        available_at=datetime(1999, 1, 1, tzinfo=UTC),
    )
    async with integration_database() as session:
        session.add(event)
        await session.commit()
        event_id = event.id
    broker = RecordingBroker(failure=ConnectionError("synthetic outage"))
    publisher = OutboxPublisher(
        integration_database, cast(Any, broker), owner="qa-repeated-outage", batch_size=1
    )
    for _ in range(7):
        async with integration_database() as session, session.begin():
            await session.execute(
                update(OutboxEvent)
                .where(OutboxEvent.id == event_id)
                .values(available_at=datetime(1999, 1, 1, tzinfo=UTC))
            )
        assert await publisher.publish_batch() == 1
    broker.failure = None
    async with integration_database() as session, session.begin():
        await session.execute(
            update(OutboxEvent)
            .where(OutboxEvent.id == event_id)
            .values(available_at=datetime(1999, 1, 1, tzinfo=UTC))
        )
    assert await publisher.publish_batch() == 1
    async with integration_database() as session:
        row = await session.get(OutboxEvent, event_id)
        assert row.delivered_at is not None
        assert row.attempts == 8


async def test_invalid_outbox_is_visibly_quarantined_without_publishing(integration_database):
    event = OutboxEvent(
        topic="qa.invalid.v2",
        payload={"body_md": "must never reach broker"},
        created_at=datetime(1998, 1, 1, tzinfo=UTC),
        available_at=datetime(1998, 1, 1, tzinfo=UTC),
    )
    async with integration_database() as session:
        session.add(event)
        await session.commit()
        event_id = event.id
    broker = RecordingBroker()
    publisher = OutboxPublisher(
        integration_database, cast(Any, broker), owner="qa-invalid", batch_size=1
    )
    await publisher.publish_batch()
    assert not broker.calls
    async with integration_database() as session:
        row = await session.get(OutboxEvent, event_id)
        assert row.last_error == "permanent:ValueError"
        assert row.delivered_at is None
    assert event_id not in await publisher._claim()


async def test_broker_value_error_is_retried_instead_of_quarantined(integration_database):
    event = OutboxEvent(
        topic="qa.broker-value-error.v2",
        payload={"revision": 1},
        created_at=datetime(1997, 1, 1, tzinfo=UTC),
        available_at=datetime(1997, 1, 1, tzinfo=UTC),
    )
    async with integration_database() as session:
        session.add(event)
        await session.commit()
        event_id = event.id
    publisher = OutboxPublisher(
        integration_database,
        cast(Any, RecordingBroker(failure=ValueError("transient broker failure"))),
        owner="qa-broker-value-error",
        batch_size=1,
    )

    assert await publisher.publish_batch() == 1
    async with integration_database() as session:
        row = await session.get(OutboxEvent, event_id)
        assert row is not None
        assert row.last_error == "ValueError"
        assert row.delivered_at is None
    async with integration_database() as session, session.begin():
        await session.execute(
            update(OutboxEvent)
            .where(OutboxEvent.id == event_id)
            .values(available_at=datetime(1997, 1, 2, tzinfo=UTC))
        )
    recovered = OutboxPublisher(
        integration_database,
        cast(Any, RecordingBroker()),
        owner="qa-broker-value-error-recovery",
        batch_size=1,
    )
    assert await recovered.publish_batch() == 1
    async with integration_database() as session:
        row = await session.get(OutboxEvent, event_id)
        assert row is not None and row.delivered_at is not None
