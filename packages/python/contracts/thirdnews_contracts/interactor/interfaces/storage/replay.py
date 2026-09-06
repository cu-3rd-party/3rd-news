from abc import ABC, abstractmethod


class ReplayStorage(ABC):
    @abstractmethod
    def accept_once(self, token_id: str, expires_at: int) -> bool:
        raise NotImplementedError
