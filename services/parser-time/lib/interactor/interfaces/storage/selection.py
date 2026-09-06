from abc import ABC, abstractmethod

from ....domain.entities.run_result import RunResult
from ....domain.entities.selection import Selection


class SelectionStorage(ABC):
    @abstractmethod
    def selected(self) -> list[Selection]:
        raise NotImplementedError

    @abstractmethod
    def is_selected(self, team: str, channel: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def runs(self) -> dict[str, RunResult]:
        raise NotImplementedError

    @abstractmethod
    def add(self, selection: Selection) -> bool:
        raise NotImplementedError

    @abstractmethod
    def remove(self, team: str, channel: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def replace_all(self, selections: list[Selection]) -> None:
        raise NotImplementedError

    @abstractmethod
    def record_run(self, team: str, channel: str, result: RunResult) -> None:
        raise NotImplementedError

    @abstractmethod
    def set_authors(self, team: str, channel: str, authors: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def set_display_name(self, team: str, channel: str, display_name: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def seed(self, selections: list[Selection]) -> None:
        raise NotImplementedError
