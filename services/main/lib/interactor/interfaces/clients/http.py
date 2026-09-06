from collections.abc import Awaitable, Callable
from typing import Protocol

from lib.dto.fetch_result import FetchResult


class HttpClient(Protocol):
    async def fetch_bytes(self, url: str, *, max_bytes: int | None = None) -> FetchResult: ...

    async def post_bytes(
        self,
        url: str,
        body: bytes,
        *,
        headers: dict[str, str] | None = None,
        max_bytes: int | None = None,
    ) -> FetchResult: ...

    async def stream_to(
        self,
        url: str,
        sink: Callable[[bytes], Awaitable[None]],
        *,
        max_bytes: int | None = None,
    ) -> tuple[str, int, str | None, int]: ...

    async def validate_url(self, url: str) -> tuple[str, ...]: ...
