import hashlib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import aiohttp

from ...dto.batch_ingest_result import BatchIngestResult
from ...dto.complete_upload_request import CompleteUploadRequest
from ...dto.completed_upload import CompletedUpload
from ...dto.ingest_result import IngestResult
from ...dto.news_batch_request import BatchSubmission, NewsBatchRequest
from ...dto.news_submission import NewsSubmission
from ...dto.upload_intent import UploadIntent
from ...dto.upload_intent_request import UploadIntentRequest
from ...interactor.errors.ingest import IngestError
from ...interactor.interfaces.clients.ingest import IngestGateway


class IngestClient(IngestGateway):
    def __init__(
        self,
        base_url: str,
        api_key: str,
        timeout: float = 30.0,
        session: aiohttp.ClientSession | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.session = session

    @property
    def headers(self) -> dict[str, str]:
        return {"X-API-Key": self.api_key}

    async def _post(self, path: str, **kwargs: Any) -> tuple[int, Any, str]:
        owned = self.session is None
        session = self.session or aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=self.timeout)
        )
        try:
            async with session.post(
                f"{self.base_url}{path}", headers=self.headers, **kwargs
            ) as response:
                text = await response.text()
                data = await response.json(content_type=None) if text else None
                return response.status, data, text
        finally:
            if owned:
                await session.close()

    async def submit(
        self,
        news: NewsSubmission,
        files: Mapping[str, Path | tuple[str, bytes, str]] | None = None,
    ) -> IngestResult:
        if files:
            raise ValueError("v2 uses upload intents; inline multipart files are unsupported")
        status, data, text = await self._post(
            "/api/v1/news", json=news.model_dump(mode="json", exclude_none=True)
        )
        if status >= 400:
            raise IngestError(status, text)
        if status != 202:
            raise IngestError(status, "expected 202 Accepted")
        return IngestResult.model_validate(data)

    async def submit_many(self, items: list[NewsSubmission]) -> BatchIngestResult:
        batch_items: list[BatchSubmission] = list(items)
        request = NewsBatchRequest(items=batch_items)
        status, data, text = await self._post(
            "/api/v1/news/batch",
            json=request.model_dump(mode="json", exclude_none=True),
        )
        if status >= 400:
            raise IngestError(status, text)
        if status != 202:
            raise IngestError(status, "expected 202 Accepted")
        return BatchIngestResult.model_validate(data)

    async def upload(self, filename: str, content_type: str, data: bytes) -> CompletedUpload:
        digest = hashlib.sha256(data).hexdigest()
        request = UploadIntentRequest(
            filename=filename,
            content_type=content_type,
            size=len(data),
            sha256=digest,
        )
        status, payload, text = await self._post(
            "/api/v1/uploads/presign", json=request.model_dump(mode="json")
        )
        if status >= 400:
            raise IngestError(status, text)
        if status != 201:
            raise IngestError(status, "expected 201 Created")
        intent = UploadIntent.model_validate(payload)
        owned = self.session is None
        session = self.session or aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=self.timeout)
        )
        try:
            async with session.put(str(intent.url), data=data, headers=intent.headers) as response:
                body = await response.text()
                if response.status >= 400:
                    raise IngestError(response.status, body)
        finally:
            if owned:
                await session.close()
        complete = CompleteUploadRequest(upload_id=intent.upload_id)
        status, payload, text = await self._post(
            "/api/v1/uploads/complete", json=complete.model_dump(mode="json")
        )
        if status >= 400:
            raise IngestError(status, text)
        result = CompletedUpload.model_validate(payload)
        if result.size != len(data) or result.sha256 != digest:
            raise IngestError(status, "completed object does not match local bytes")
        return result
