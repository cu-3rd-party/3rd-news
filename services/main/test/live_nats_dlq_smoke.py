from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any, cast

from lib.core.config import Settings
from lib.infra.clients.nats import DurableConsumer, JetStreamBroker, StreamSettings


class OneDlqOutage:
    def __init__(self, broker: JetStreamBroker, recorded: asyncio.Event) -> None:
        self._broker = broker
        self._recorded = recorded
        self.failed_once = False
        self.dlq_calls = 0

    @property
    def jetstream(self):
        return self._broker.jetstream

    async def publish_json(self, subject, payload, *, message_id, headers=None):
        if subject.startswith("dead."):
            self.dlq_calls += 1
            if not self.failed_once:
                self.failed_once = True
                raise ConnectionError("simulated DLQ outage")
        sequence = await self._broker.publish_json(
            subject,
            payload,
            message_id=message_id,
            headers=headers,
        )
        if subject.startswith("dead."):
            self._recorded.set()
        return sequence


async def main() -> None:
    nonce = uuid.uuid4().hex[:12]
    stream = f"QADLQ{nonce.upper()}"
    subject = f"qa.dlq.{nonce}"
    durable = f"qa-dlq-{nonce}"
    event_id = str(uuid.uuid4())
    broker = JetStreamBroker(
        Settings().broker_url,
        settings=StreamSettings(
            name=stream,
            subjects=(subject,),
            max_age_seconds=300,
            duplicate_window_seconds=60,
        ),
        client_name=f"qa-dlq-{nonce}",
    )
    recorded = asyncio.Event()
    deliveries: list[int] = []
    try:
        await broker.connect()
        proxy = OneDlqOutage(broker, recorded)
        consumer = DurableConsumer(
            cast(Any, proxy),
            stream=stream,
            subject=subject,
            durable=durable,
            max_deliver=3,
            ack_wait_seconds=1,
            batch_size=1,
        )
        stop = asyncio.Event()

        async def fail(message) -> None:
            deliveries.append(message.deliveries)
            raise RuntimeError("malicious content must not enter the DLQ")

        task = asyncio.create_task(consumer.run(fail, stop=stop))
        for _ in range(50):
            try:
                initial_consumer_info = await broker.jetstream.consumer_info(stream, durable)
            except Exception:
                await asyncio.sleep(0.05)
            else:
                break
        else:
            raise AssertionError("durable consumer was not created")
        assert initial_consumer_info.config.max_deliver == -1
        await broker.publish_json(
            subject,
            {"body_md": "private payload"},
            message_id=event_id,
            headers={"X-Event-Id": event_id},
        )
        try:
            await asyncio.wait_for(recorded.wait(), timeout=20)
        except TimeoutError:
            raise AssertionError(
                f"DLQ recovery timed out after deliveries={deliveries}, "
                f"publish_attempts={proxy.dlq_calls}"
            ) from None
        stop.set()
        await asyncio.wait_for(task, timeout=3)

        assert deliveries == [1, 2, 3, 4], deliveries
        assert proxy.failed_once and proxy.dlq_calls == 2
        dead_stream = f"{stream}_DLQ"
        info = await broker.jetstream.stream_info(dead_stream)
        assert info.state.messages == 1
        stored = await broker.jetstream.get_msg(dead_stream, seq=info.state.first_seq)
        assert stored.data is not None
        payload = json.loads(stored.data)
        assert payload == {
            "consumer": durable,
            "error_code": "RuntimeError",
            "event_id": event_id,
            "stream_sequence": 1,
        }
        consumer_info = await broker.jetstream.consumer_info(stream, durable)
        assert consumer_info.num_ack_pending == 0
        print(
            json.dumps(
                {
                    "deliveries": deliveries,
                    "dlq_publish_attempts": proxy.dlq_calls,
                    "dlq_messages": info.state.messages,
                    "original_ack_pending": consumer_info.num_ack_pending,
                },
                sort_keys=True,
            )
        )
    finally:
        try:
            jetstream = broker.jetstream
        except RuntimeError:
            pass
        else:
            for name in (f"{stream}_DLQ", stream):
                try:
                    await jetstream.delete_stream(name)
                except Exception:
                    pass
        await broker.close()


if __name__ == "__main__":
    asyncio.run(main())
