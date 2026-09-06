from abc import ABC, abstractmethod


class HealthStorage(ABC):
    ready: bool

    @abstractmethod
    def record_cycle(self, succeeded: bool) -> None:
        raise NotImplementedError
