class RecordingReplacementClient:
    index = "qa-fresh-projection"

    def __init__(self) -> None:
        self.documents: list[dict] = []

    async def replace_all(self, documents, **kwargs) -> int:
        del kwargs
        self.documents = [document async for document in documents]
        return len(self.documents)
