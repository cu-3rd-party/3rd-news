from abc import ABC, abstractmethod


class FeedClient(ABC):
    @abstractmethod
    async def fetch(self, url: str) -> bytes:
        raise NotImplementedError
