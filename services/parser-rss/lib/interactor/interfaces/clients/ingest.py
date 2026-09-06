from abc import ABC, abstractmethod

from thirdnews_contracts import IngestResult, NewsSubmission


class IngestGateway(ABC):
    @abstractmethod
    async def submit(self, news: NewsSubmission) -> IngestResult:
        raise NotImplementedError
