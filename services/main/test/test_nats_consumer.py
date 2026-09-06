from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace
from typing import Any, cast

import pytest
from lib.infra.clients.nats.consumer import DurableConsumer

from .fakes.raw_message import RawMessage
from .fakes.recording_broker import RecordingBroker


def consumer(broker) -> DurableConsumer:
    return DurableConsumer(
        cast(Any, broker),
        stream="QA",
        subject="qa.>",
        durable="qa-worker",
        max_deliver=3,
        ack_wait_seconds=120,
    )


@pytest.mark.asyncio
async def test_run_repairs_existing_durable_cap_and_unsubscribes_on_stop() -> None:
    class Subscription:
        unsubscribed = 0

        async def unsubscribe(self) -> None:
            self.unsubscribed += 1

    class JetStream:
        def __init__(self) -> None:
            self.config = None
            self.subscription = Subscription()

        async def stream_info(self, name):
            assert name == "QA_DLQ"
            return object()

        async def add_consumer(self, stream, *, config):
            assert stream == "QA"
            self.config = config

        async def pull_subscribe(self, subject, *, durable, stream, config):
            assert (subject, durable, stream) == ("qa.>", "qa-worker", "QA")
            assert config is self.config
            return self.subscription

    broker = SimpleNamespace(jetstream=JetStream())
    stop = asyncio.Event()
    stop.set()

    async def unused_handler(message) -> None:
        raise AssertionError(message)

    await consumer(broker).run(unused_handler, stop=stop)

    assert broker.jetstream.config.max_deliver == -1
    assert broker.jetstream.subscription.unsubscribed == 1


@pytest.mark.asyncio
async def test_failure_before_budget_naks_with_bounded_backoff() -> None:
    broker = RecordingBroker()
    raw = RawMessage(deliveries=2, sequence=41, event_id=str(uuid.uuid4()))

    await consumer(broker).record_failure(cast(Any, raw), RuntimeError("private body"))

    assert raw.naks == [4]
    assert raw.acks == 0
    assert broker.calls == []


@pytest.mark.asyncio
async def test_exhausted_failure_is_acked_only_after_identifier_only_dlq_record() -> None:
    broker = RecordingBroker()
    event_id = str(uuid.uuid4())
    raw = RawMessage(deliveries=3, sequence=42, event_id=event_id)

    await consumer(broker).record_failure(
        cast(Any, raw), RuntimeError("secret payload content must never be persisted")
    )

    assert raw.acks == 1
    assert raw.naks == []
    assert broker.calls == [
        (
            "dead.QA.qa-worker",
            {
                "event_id": event_id,
                "consumer": "qa-worker",
                "stream_sequence": 42,
                "error_code": "RuntimeError",
            },
            "dead:qa-worker:42",
        )
    ]
    assert "secret" not in repr(broker.calls)


@pytest.mark.asyncio
async def test_dlq_outage_leaves_original_unacked_for_recovery() -> None:
    broker = RecordingBroker(ConnectionError("DLQ unavailable"))
    raw = RawMessage(deliveries=7, sequence=43, event_id="malformed-secret-event-id")

    await consumer(broker).record_failure(cast(Any, raw), ValueError("sensitive malformed body"))

    assert raw.acks == 0
    assert raw.naks == [120]
    assert broker.calls[0][1] == {
        "event_id": None,
        "consumer": "qa-worker",
        "stream_sequence": 43,
        "error_code": "ValueError",
    }
