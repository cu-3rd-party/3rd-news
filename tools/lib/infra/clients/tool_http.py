from typing import Any, Self

from thirdnews_contracts import ToolClient, ToolResponse

from ...interactor.interfaces.clients.http import HttpClient


class ToolHttpClient(HttpClient):
    def __init__(self, base_url: str, timeout: float = 60.0) -> None:
        self._client = ToolClient(base_url=base_url, timeout=timeout)

    @property
    def headers(self) -> dict[str, str]:
        return self._client.headers

    def get(self, path: str, **kwargs: Any) -> ToolResponse:
        return self._client.get(path, **kwargs)

    def post(self, path: str, **kwargs: Any) -> ToolResponse:
        return self._client.post(path, **kwargs)

    def put(self, path: str, **kwargs: Any) -> ToolResponse:
        return self._client.put(path, **kwargs)

    def patch(self, path: str, **kwargs: Any) -> ToolResponse:
        return self._client.patch(path, **kwargs)

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None
