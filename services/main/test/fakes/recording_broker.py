class RecordingBroker:
    def __init__(self, failure: Exception | None = None) -> None:
        self.failure = failure
        self.calls: list[tuple[str, dict, str]] = []

    async def publish_json(self, subject, payload, *, message_id, headers=None):
        del headers
        self.calls.append((subject, dict(payload), message_id))
        if self.failure is not None:
            raise self.failure
        return 1
