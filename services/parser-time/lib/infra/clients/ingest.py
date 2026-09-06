import aiohttp
from thirdnews_contracts import CompletedUpload, IngestClient, IngestResult, NewsSubmission

from ...interactor.interfaces.clients.ingest import IngestGateway


class NewsIngestClient(IngestGateway):
    def __init__(self, base_url: str, api_key: str, session: aiohttp.ClientSession) -> None:
        self._client = IngestClient(base_url, api_key, session=session)

    async def submit(self, news: NewsSubmission) -> IngestResult:
        return await self._client.submit(news)

    async def upload(self, filename: str, content_type: str, data: bytes) -> CompletedUpload:
        return await self._client.upload(filename, content_type, data)
