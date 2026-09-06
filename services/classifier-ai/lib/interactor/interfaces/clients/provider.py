from abc import ABC, abstractmethod
from typing import Any


class ProviderClient(ABC):
    @abstractmethod
    async def complete(self, payload: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError
