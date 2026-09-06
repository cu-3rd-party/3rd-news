from __future__ import annotations

import asyncio
import uuid

from lib.infra.clients.nats import DurableConsumer, JetStreamBroker, StreamSettings


async def exercise(url: str | None = None) -> tuple[int, list[int]]:
    if url is None:
        from lib.core.config import Settings

        url = Settings().broker_url
    nonce = uuid.uuid4().hex
    stream = f"QA_{nonce.upper()}"
    subject = f"qa.{nonce}.event"
    durable = f"qa-{nonce}"
    broker = JetStreamBroker(
        url,
        settings=StreamSettings(
            name=stream,
            subjects=(subject,),
            max_age_seconds=60,
            duplicate_window_seconds=30,
        ),
        client_name=durable,
    )
    deliveries: list[int] = []
    stop = asyncio.Event()
    try:
        await broker.connect()
        first_sequence = await broker.publish_json(
            subject,
            {"event_id": nonce},
            message_id=nonce,
        )
        duplicate_sequence = await broker.publish_json(
            subject,
            {"event_id": nonce},
            message_id=nonce,
        )
        assert duplicate_sequence == first_sequence

        async def fail_once(message) -> None:
            deliveries.append(message.deliveries)
            if len(deliveries) == 1:
                raise RuntimeError("force one NAK")
            stop.set()

        consumer = DurableConsumer(
            broker,
            stream=stream,
            subject=subject,
            durable=durable,
            max_deliver=3,
            ack_wait_seconds=1,
            batch_size=1,
        )
        await asyncio.wait_for(consumer.run(fail_once, stop=stop), timeout=8)
        assert deliveries == [1, 2]
        return first_sequence, deliveries
    finally:
        if broker._js is not None:
            await broker.jetstream.delete_stream(stream)
            await broker.jetstream.delete_stream(f"{stream}_DLQ")
        await broker.close()


if __name__ == "__main__":
    sequence, observed = asyncio.run(exercise())
    print(f"JetStream dedupe sequence={sequence}; deliveries={observed}")
