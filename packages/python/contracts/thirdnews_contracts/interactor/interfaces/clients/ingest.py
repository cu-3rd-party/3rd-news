from abc import ABC, abstractmethod
from collections.abc import Mapping
from pathlib import Path

from ....dto.batch_ingest_result import BatchIngestResult
from ....dto.completed_upload import CompletedUpload
from ....dto.ingest_result import IngestResult
from ....dto.news_submission import NewsSubmission


class IngestGateway(ABC):
    @abstractmethod
    async def submit(
        self,
        news: NewsSubmission,
        files: Mapping[str, Path | tuple[str, bytes, str]] | None = None,
    ) -> IngestResult:
        raise NotImplementedError

    @abstractmethod
    async def submit_many(self, items: list[NewsSubmission]) -> BatchIngestResult:
        raise NotImplementedError

    @abstractmethod
    async def upload(self, filename: str, content_type: str, data: bytes) -> CompletedUpload:
        raise NotImplementedError
