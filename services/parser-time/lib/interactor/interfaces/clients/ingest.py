from abc import ABC, abstractmethod

from thirdnews_contracts import CompletedUpload, IngestResult, NewsSubmission


class IngestGateway(ABC):
    @abstractmethod
    async def submit(self, news: NewsSubmission) -> IngestResult:
        raise NotImplementedError

    @abstractmethod
    async def upload(self, filename: str, content_type: str, data: bytes) -> CompletedUpload:
        raise NotImplementedError
