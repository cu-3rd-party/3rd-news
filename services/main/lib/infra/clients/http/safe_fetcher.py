from __future__ import annotations

import asyncio
import ipaddress
import socket
from collections.abc import AsyncIterator, Awaitable, Callable, Collection
from typing import Final
from urllib.parse import urljoin, urlsplit

import aiohttp
from lib.dto.fetch_result import FetchResult
from lib.dto.resolved_target import ResolvedTarget
from lib.dto.url_policy import UrlPolicy
from lib.interactor.errors.fetch_limit import FetchLimitError
from lib.interactor.errors.ssrf_blocked import SsrfBlockedError
from lib.interactor.interfaces.clients.http import HttpClient

from .pinned_resolver import PinnedResolver

_REDIRECTS: Final = frozenset({301, 302, 303, 307, 308})


class SafeFetcher(HttpClient):
    def __init__(
        self,
        *,
        policy: UrlPolicy | None = None,
        timeout_seconds: float = 15.0,
        max_bytes: int = 10_000_000,
        resolver: Callable[[str, int], Awaitable[Collection[str]]] | None = None,
    ) -> None:
        if max_bytes < 1:
            raise ValueError("max_bytes must be positive")
        self._policy = policy or UrlPolicy()
        self._timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        self._max_bytes = max_bytes
        self._resolver = resolver or self._resolve_dns

    async def fetch_bytes(self, url: str, *, max_bytes: int | None = None) -> FetchResult:
        chunks: list[bytes] = []
        final_url = url
        status = 0
        content_type: str | None = None
        total = 0

        async def collect(chunk: bytes) -> None:
            nonlocal total
            chunks.append(chunk)
            total += len(chunk)

        final_url, status, content_type, _ = await self.stream_to(url, collect, max_bytes=max_bytes)
        return FetchResult(final_url, status, content_type, total, b"".join(chunks))

    async def post_bytes(
        self,
        url: str,
        body: bytes,
        *,
        headers: dict[str, str] | None = None,
        max_bytes: int | None = None,
    ) -> FetchResult:

        limit = self._limit(max_bytes)
        target = await self._validated_target(url)
        connector = aiohttp.TCPConnector(
            resolver=PinnedResolver(target),
            use_dns_cache=False,
            limit=1,
            ttl_dns_cache=0,
        )
        async with aiohttp.ClientSession(
            connector=connector,
            timeout=self._timeout,
            auto_decompress=False,
            raise_for_status=False,
        ) as session:
            async with session.post(
                url,
                data=body,
                headers={"Accept-Encoding": "identity", **(headers or {})},
                allow_redirects=False,
            ) as response:
                self._verify_peer(response, target)
                response_body = await self._read_bounded(response, limit)
                return FetchResult(
                    url,
                    response.status,
                    response.content_type or None,
                    len(response_body),
                    response_body,
                )

    async def iter_bytes(self, url: str, *, max_bytes: int | None = None) -> AsyncIterator[bytes]:
        queue: asyncio.Queue[bytes | BaseException | None] = asyncio.Queue(maxsize=2)

        async def sink(chunk: bytes) -> None:
            await queue.put(chunk)

        async def produce() -> None:
            try:
                await self.stream_to(url, sink, max_bytes=max_bytes)
            except BaseException as exc:
                await queue.put(exc)
            finally:
                await queue.put(None)

        task = asyncio.create_task(produce())
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                if isinstance(item, BaseException):
                    raise item
                yield item
        finally:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def stream_to(
        self,
        url: str,
        sink: Callable[[bytes], Awaitable[None]],
        *,
        max_bytes: int | None = None,
    ) -> tuple[str, int, str | None, int]:
        limit = self._limit(max_bytes)
        current = url
        for hop in range(self._policy.max_redirects + 1):
            target = await self._validated_target(current)
            connector = aiohttp.TCPConnector(
                resolver=PinnedResolver(target),
                use_dns_cache=False,
                limit=1,
                ttl_dns_cache=0,
            )
            async with aiohttp.ClientSession(
                connector=connector,
                timeout=self._timeout,
                auto_decompress=False,
                raise_for_status=False,
            ) as session:
                async with session.get(
                    current,
                    allow_redirects=False,
                    headers={"Accept-Encoding": "identity"},
                ) as response:
                    self._verify_peer(response, target)
                    if response.status in _REDIRECTS:
                        location = response.headers.get("Location")
                        if not location:
                            raise aiohttp.ClientResponseError(
                                response.request_info,
                                response.history,
                                status=response.status,
                                message="redirect has no Location header",
                            )
                        if hop >= self._policy.max_redirects:
                            raise SsrfBlockedError("too many redirects")
                        current = urljoin(current, location)
                        continue
                    response.raise_for_status()
                    total = await self._stream_bounded(response, sink, limit)
                    return current, response.status, response.content_type or None, total
        raise SsrfBlockedError("too many redirects")

    async def validate_url(self, url: str) -> tuple[str, ...]:
        return (await self._validated_target(url)).addresses

    def _limit(self, requested: int | None) -> int:
        limit = self._max_bytes if requested is None else min(requested, self._max_bytes)
        if limit < 1:
            raise ValueError("max_bytes must be positive")
        return limit

    async def _read_bounded(self, response: aiohttp.ClientResponse, limit: int) -> bytes:
        chunks: list[bytes] = []

        async def collect(chunk: bytes) -> None:
            chunks.append(chunk)

        await self._stream_bounded(response, collect, limit)
        return b"".join(chunks)

    async def _stream_bounded(
        self,
        response: aiohttp.ClientResponse,
        sink: Callable[[bytes], Awaitable[None]],
        limit: int,
    ) -> int:
        declared = self._declared_size(response.headers.get("Content-Length"))
        if declared is not None and declared > limit:
            raise FetchLimitError(f"declared response size {declared} exceeds limit {limit}")
        total = 0
        async for chunk in response.content.iter_chunked(64 * 1024):
            total += len(chunk)
            if total > limit:
                raise FetchLimitError(f"response exceeds limit {limit}")
            await sink(chunk)
        return total

    async def _validated_target(self, url: str) -> ResolvedTarget:
        parts = urlsplit(url)
        if parts.scheme.lower() not in self._policy.allowed_schemes:
            raise SsrfBlockedError("only http and https URLs are allowed")
        if parts.username is not None or parts.password is not None:
            raise SsrfBlockedError("userinfo in a URL is not allowed")
        if not parts.hostname:
            raise SsrfBlockedError("URL has no host")
        host = parts.hostname.rstrip(".").lower()
        try:
            port = parts.port or (443 if parts.scheme.lower() == "https" else 80)
        except ValueError as exc:
            raise SsrfBlockedError("invalid port") from exc
        addresses = tuple(dict.fromkeys(await self._resolver(host, port)))
        if not addresses:
            raise SsrfBlockedError("host did not resolve")
        trusted_service = host in self._policy.allowed_hosts
        for address in addresses:
            try:
                parsed = ipaddress.ip_address(address)
            except ValueError as exc:
                raise SsrfBlockedError("resolver returned a non-IP address") from exc
            if not trusted_service and not parsed.is_global:
                raise SsrfBlockedError(f"address {address} is not globally routable")
        return ResolvedTarget(host=host, port=port, addresses=addresses)

    @staticmethod
    async def _resolve_dns(host: str, port: int) -> Collection[str]:
        loop = asyncio.get_running_loop()
        records = await loop.getaddrinfo(
            host,
            port,
            family=socket.AF_UNSPEC,
            type=socket.SOCK_STREAM,
            proto=socket.IPPROTO_TCP,
        )
        return [str(record[4][0]) for record in records]

    @staticmethod
    def _verify_peer(response: aiohttp.ClientResponse, target: ResolvedTarget) -> None:
        connection = response.connection
        transport = connection.transport if connection is not None else None
        peer = transport.get_extra_info("peername") if transport is not None else None
        if peer is None:
            return
        address = str(peer[0])
        if address not in target.addresses:
            raise SsrfBlockedError("remote peer changed after DNS validation")

    @staticmethod
    def _declared_size(raw: str | None) -> int | None:
        if raw is None:
            return None
        try:
            value = int(raw)
        except ValueError as exc:
            raise FetchLimitError("invalid Content-Length") from exc
        if value < 0:
            raise FetchLimitError("invalid Content-Length")
        return value
