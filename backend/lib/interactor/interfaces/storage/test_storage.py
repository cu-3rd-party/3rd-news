from abc import ABC, abstractmethod


class TestStorageInterface(ABC):
    @abstractmethod
    async def test(self) -> bool:
        raise NotImplementedError
