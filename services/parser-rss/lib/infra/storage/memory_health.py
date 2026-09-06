from ...interactor.interfaces.storage.health import HealthStorage


class MemoryHealthStorage(HealthStorage):
    def __init__(self) -> None:
        self.ready = False

    def record_cycle(self, succeeded: bool) -> None:
        self.ready = succeeded
