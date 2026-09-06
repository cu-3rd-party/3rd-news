from types import SimpleNamespace


class RawMessage:
    def __init__(self, *, deliveries: int, sequence: int, event_id: str | None) -> None:
        self.metadata = SimpleNamespace(
            num_delivered=deliveries,
            sequence=SimpleNamespace(stream=sequence),
        )
        self.headers = {"X-Event-Id": event_id} if event_id is not None else {}
        self.acks = 0
        self.naks: list[int | None] = []

    async def ack_sync(self) -> None:
        self.acks += 1

    async def nak(self, *, delay=None) -> None:
        self.naks.append(delay)
