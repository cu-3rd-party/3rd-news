from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Awaitable, Callable

from lib.dto.incoming_message import IncomingMessage
from lib.interactor.interfaces.clients.consumer import ConsumerClient

from nats.aio.msg import Msg
from nats.js.api import AckPolicy, ConsumerConfig, DeliverPolicy, StorageType, StreamConfig
from nats.js.errors import FetchTimeoutError, NotFoundError

from .jetstream import JetStreamBroker


class DurableConsumer(ConsumerClient):
    def __init__(
        self,
        broker: JetStreamBroker,
        *,
        stream: str,
        subject: str,
        durable: str,
        max_deliver: int = 5,
        ack_wait_seconds: int = 120,
        batch_size: int = 20,
    ) -> None:
        self._broker = broker
        self._stream = stream
        self._subject = subject
        self._durable = durable
        self._max_deliver = max_deliver
        self._ack_wait = ack_wait_seconds
        self._batch_size = batch_size

    async def run(
        self,
        handler: Callable[[IncomingMessage], Awaitable[None]],
        *,
        stop: asyncio.Event,
    ) -> None:
        dead_stream = f"{self._stream}_DLQ"
        try:
            await self._broker.jetstream.stream_info(dead_stream)
        except NotFoundError:
            await self._broker.jetstream.add_stream(
                config=StreamConfig(
                    name=dead_stream, subjects=[f"dead.{self._stream}.>"], storage=StorageType.FILE
                )
            )
        config = ConsumerConfig(
            durable_name=self._durable,
            filter_subject=self._subject,
            deliver_policy=DeliverPolicy.ALL,
            ack_policy=AckPolicy.EXPLICIT,
            ack_wait=self._ack_wait,
            max_deliver=-1,
        )

        await self._broker.jetstream.add_consumer(self._stream, config=config)
        subscription = await self._broker.jetstream.pull_subscribe(
            self._subject,
            durable=self._durable,
            stream=self._stream,
            config=config,
        )
        try:
            while not stop.is_set():
                try:
                    messages = await subscription.fetch(batch=self._batch_size, timeout=1.0)
                except FetchTimeoutError, TimeoutError:
                    continue
                for raw in messages:
                    if stop.is_set():
                        await raw.nak()
                        return
                    try:
                        message = self._decode(raw)
                        await handler(message)
                    except asyncio.CancelledError:
                        await raw.nak()
                        raise
                    except Exception as error:
                        await self.record_failure(raw, error)
                    else:
                        await raw.ack_sync()
        finally:
            await subscription.unsubscribe()

    async def record_failure(self, raw: Msg, error: Exception) -> None:
        metadata = raw.metadata
        deliveries = int(metadata.num_delivered)
        if deliveries < self._max_deliver:
            await raw.nak(delay=min(2 ** min(deliveries, 8), self._ack_wait))
            return
        candidate = (raw.headers or {}).get("X-Event-Id") or (raw.headers or {}).get("Nats-Msg-Id")
        try:
            event_id = str(uuid.UUID(candidate or ""))
        except ValueError:
            event_id = None

        failure = {
            "event_id": event_id,
            "consumer": self._durable,
            "stream_sequence": metadata.sequence.stream,
            "error_code": type(error).__name__,
        }
        try:
            await self._broker.publish_json(
                f"dead.{self._stream}.{self._durable}",
                failure,
                message_id=f"dead:{self._durable}:{metadata.sequence.stream}",
            )
            await raw.ack_sync()
        except Exception:
            await raw.nak(delay=self._ack_wait)

    @staticmethod
    def _decode(raw: Msg) -> IncomingMessage:
        payload = json.loads(raw.data)
        if not isinstance(payload, dict):
            raise ValueError("event payload must be a JSON object")
        headers = raw.headers or {}
        message_id = headers.get("X-Event-Id") or headers.get("Nats-Msg-Id")
        if not message_id:
            raise ValueError("event has no stable message id")
        metadata = raw.metadata
        deliveries = int(metadata.num_delivered) if metadata is not None else 1
        return IncomingMessage(
            id=message_id,
            subject=raw.subject,
            payload=payload,
            deliveries=deliveries,
        )
