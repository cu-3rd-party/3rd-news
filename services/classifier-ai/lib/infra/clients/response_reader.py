import json
from typing import Any

import aiohttp


async def bounded_json(
    response: aiohttp.ClientResponse,
    max_bytes: int,
) -> dict[str, Any]:
    chunks: list[bytes] = []
    size = 0
    async for chunk in response.content.iter_chunked(64 * 1024):
        size += len(chunk)
        if size > max_bytes:
            raise ValueError("provider response exceeds configured byte limit")
        chunks.append(chunk)
    parsed = json.loads(b"".join(chunks))
    if not isinstance(parsed, dict):
        raise TypeError("provider response envelope is not an object")
    return parsed
