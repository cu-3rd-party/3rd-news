from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from lib.dto.stream_settings import StreamSettings
from lib.interactor.interfaces.clients.broker import BrokerClient

import nats
from nats.aio.client import Client as NatsClient
from nats.js.api import RetentionPolicy, StorageType, StreamConfig
from nats.js.client import JetStreamContext
from nats.js.errors import NotFoundError


class JetStreamBroker(BrokerClient):
    def __init__(
        self,
        url: str,
        *,
        settings: StreamSettings | None = None,
        client_name: str = "thirdnews",
        connect_timeout: float = 5.0,
    ) -> None:
        self._url = url
        self._settings = settings or StreamSettings()
        self._client_name = client_name
        self._connect_timeout = connect_timeout
        self._connection: NatsClient | None = None
        self._js: JetStreamContext | None = None

    @property
    def jetstream(self) -> JetStreamContext:
        if self._js is None:
            raise RuntimeError("JetStreamBroker is not connected")
        return self._js

    async def connect(self) -> JetStreamBroker:
        if self._connection is not None and self._connection.is_connected:
            return self
        self._connection = await nats.connect(
            servers=[self._url],
            name=self._client_name,
            connect_timeout=self._connect_timeout,
            allow_reconnect=True,
            max_reconnect_attempts=-1,
        )
        self._js = self._connection.jetstream()
        await self._ensure_stream()
        return self

    async def close(self) -> None:
        connection, self._connection, self._js = self._connection, None, None
        if connection is not None and not connection.is_closed:
            await connection.drain()

    async def publish_json(
        self,
        subject: str,
        payload: Mapping[str, Any],
        *,
        message_id: str,
        headers: Mapping[str, str] | None = None,
    ) -> int:
        encoded = json.dumps(
            payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        ).encode("utf-8")
        outgoing_headers = dict(headers or {})
        outgoing_headers["Nats-Msg-Id"] = message_id
        ack = await self.jetstream.publish(subject, encoded, headers=outgoing_headers)
        return int(ack.seq)

    async def _ensure_stream(self) -> None:
        config = StreamConfig(
            name=self._settings.name,
            subjects=list(self._settings.subjects),
            retention=RetentionPolicy.LIMITS,
            storage=StorageType.FILE,
            max_age=self._settings.max_age_seconds,
            duplicate_window=self._settings.duplicate_window_seconds,
        )
        try:
            await self.jetstream.stream_info(self._settings.name)
        except NotFoundError:
            await self.jetstream.add_stream(config=config)
        else:
            await self.jetstream.update_stream(config=config)

    async def __aenter__(self) -> JetStreamBroker:
        return await self.connect()

    async def __aexit__(self, *_: object) -> None:
        await self.close()
