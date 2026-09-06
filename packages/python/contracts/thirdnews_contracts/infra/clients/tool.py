import asyncio
from dataclasses import dataclass, field
from typing import Any, Self

import aiohttp

from ...dto.tool_response import ToolResponse
from ...interactor.interfaces.clients.tool import ToolGateway


@dataclass(slots=True)
class ToolClient(ToolGateway):
    base_url: str
    timeout: float = 60.0
    headers: dict[str, str] = field(default_factory=dict)

    async def _async_request(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        params: dict[str, Any] | None = None,
    ) -> ToolResponse:
        timeout = aiohttp.ClientTimeout(total=self.timeout)
        async with (
            aiohttp.ClientSession(timeout=timeout, headers=self.headers) as session,
            session.request(
                method, f"{self.base_url.rstrip('/')}{path}", json=json, params=params
            ) as response,
        ):
            text = await response.text()
            body = await response.json(content_type=None) if text else None
            return ToolResponse(response.status, body, text)

    def request(self, method: str, path: str, **kwargs: Any) -> ToolResponse:
        return asyncio.run(self._async_request(method, path, **kwargs))

    def get(self, path: str, **kwargs: Any) -> ToolResponse:
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs: Any) -> ToolResponse:
        return self.request("POST", path, **kwargs)

    def put(self, path: str, **kwargs: Any) -> ToolResponse:
        return self.request("PUT", path, **kwargs)

    def patch(self, path: str, **kwargs: Any) -> ToolResponse:
        return self.request("PATCH", path, **kwargs)

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None
