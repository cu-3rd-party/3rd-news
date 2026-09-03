"""Redis-backed job queue.

Small on purpose: one list per job type, `BLPOP` on the worker side, failed
jobs pushed back with an attempt counter. Enough for a few thousand items a
day; swap for RabbitMQ by reimplementing `enqueue` and `consume`.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import redis.asyncio as redis

from .config import settings

QUEUE_CLASSIFY = "3rdnews:jobs:classify"
QUEUE_MEDIA = "3rdnews:jobs:media"

_client: redis.Redis | None = None


def get_client() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.from_url(settings.redis_url, decode_responses=True)
    return _client


async def close_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


async def enqueue(queue: str, payload: dict[str, Any]) -> None:
    await get_client().rpush(queue, json.dumps(payload))


async def consume(queues: list[str], timeout: int = 5) -> AsyncIterator[tuple[str, dict]]:
    """Yield `(queue, payload)` forever, blocking between jobs."""

    client = get_client()
    while True:
        item = await client.blpop(queues, timeout=timeout)
        if item is None:
            continue
        queue, raw = item
        try:
            yield queue, json.loads(raw)
        except json.JSONDecodeError:
            continue


async def requeue(queue: str, payload: dict[str, Any], max_attempts: int) -> bool:
    """Push a failed job back. Returns False once attempts are exhausted."""

    attempts = int(payload.get("attempts", 0)) + 1
    if attempts >= max_attempts:
        return False
    payload["attempts"] = attempts
    await enqueue(queue, payload)
    return True
