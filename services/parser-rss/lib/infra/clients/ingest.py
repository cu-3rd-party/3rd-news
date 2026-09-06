from thirdnews_contracts import IngestClient, IngestResult, NewsSubmission

from ...interactor.interfaces.clients.ingest import IngestGateway


class NewsIngestClient(IngestGateway):
    def __init__(self, base_url: str, api_key: str) -> None:
        self._client = IngestClient(base_url, api_key)

    async def submit(self, news: NewsSubmission) -> IngestResult:
        return await self._client.submit(news)
