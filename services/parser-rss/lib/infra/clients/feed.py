import aiohttp

from ...interactor.interfaces.clients.feed import FeedClient


class AiohttpFeedClient(FeedClient):
    def __init__(self, timeout_s: float, max_bytes: int) -> None:
        self._timeout = aiohttp.ClientTimeout(total=timeout_s)
        self._max_bytes = max_bytes
        self._session: aiohttp.ClientSession | None = None

    async def open(self) -> None:
        self._session = aiohttp.ClientSession(timeout=self._timeout)

    async def close(self) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None

    async def fetch(self, url: str) -> bytes:
        if self._session is None:
            raise RuntimeError("feed client is not open")
        async with self._session.get(url, allow_redirects=True, max_redirects=5) as response:
            response.raise_for_status()
            chunks: list[bytes] = []
            total = 0
            async for chunk in response.content.iter_chunked(64 * 1024):
                total += len(chunk)
                if total > self._max_bytes:
                    raise ValueError("feed exceeds MAX_FEED_BYTES")
                chunks.append(chunk)
            return b"".join(chunks)
