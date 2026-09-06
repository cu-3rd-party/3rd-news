from abc import ABC, abstractmethod
from typing import Any

from ....dto.tool_response import ToolResponse


class ToolGateway(ABC):
    @abstractmethod
    def request(self, method: str, path: str, **kwargs: Any) -> ToolResponse:
        raise NotImplementedError
