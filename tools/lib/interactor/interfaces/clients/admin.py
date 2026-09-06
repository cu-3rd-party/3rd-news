from abc import ABC, abstractmethod
from collections.abc import Iterator
from typing import Any


class AdminClient(ABC):
    @abstractmethod
    def news(self, **params: Any) -> Iterator[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def set_status(self, news_id: str, status: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def set_labels(self, news_id: str, labels: dict[str, list[str]]) -> None:
        raise NotImplementedError
