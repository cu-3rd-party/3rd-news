class RecordingSearch:
    def __init__(self) -> None:
        self.kwargs: dict = {}

    async def search(self, query, **kwargs):
        self.kwargs = {"query": query, **kwargs}
        return {"hits": [], "estimatedTotalHits": 0, "facetDistribution": {}}
