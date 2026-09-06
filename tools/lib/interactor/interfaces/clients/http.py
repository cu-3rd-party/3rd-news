from abc import ABC, abstractmethod
from typing import Any

from thirdnews_contracts import ToolResponse


class HttpClient(ABC):
    @abstractmethod
    def get(self, path: str, **kwargs: Any) -> ToolResponse:
        raise NotImplementedError

    @abstractmethod
    def post(self, path: str, **kwargs: Any) -> ToolResponse:
        raise NotImplementedError

    @abstractmethod
    def put(self, path: str, **kwargs: Any) -> ToolResponse:
        raise NotImplementedError

    @abstractmethod
    def patch(self, path: str, **kwargs: Any) -> ToolResponse:
        raise NotImplementedError
