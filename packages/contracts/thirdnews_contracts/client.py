"""Minimal client for parser authors.

    from thirdnews_contracts import IngestClient, NewsSubmission

    client = IngestClient("https://news.example.edu", api_key="tnk_...")
    client.submit(NewsSubmission(body_md="...", source_text="Деканат", external_id="123"))
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx

from .ingest import IngestResult, NewsSubmission


class IngestError(RuntimeError):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(f"ingest failed [{status_code}]: {detail}")
        self.status_code = status_code
        self.detail = detail


class IngestClient:
    """Thin, dependency-light wrapper over `POST /api/v1/ingest/news`."""

    def __init__(self, base_url: str, api_key: str, timeout: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    @property
    def _headers(self) -> dict[str, str]:
        return {"X-API-Key": self.api_key}

    def submit(
        self,
        news: NewsSubmission,
        files: dict[str, Path | tuple[str, bytes, str]] | None = None,
    ) -> IngestResult:
        """Send one item. `files` maps `AttachmentInput.upload_name` to a file."""

        url = f"{self.base_url}/api/v1/ingest/news"
        payload = news.model_dump(mode="json", exclude_none=True)
        with httpx.Client(timeout=self.timeout) as http:
            if files:
                multipart = {}
                for name, item in files.items():
                    if isinstance(item, Path):
                        multipart[name] = (item.name, item.read_bytes(), "application/octet-stream")
                    else:
                        multipart[name] = item
                response = http.post(
                    url,
                    headers=self._headers,
                    data={"payload": json.dumps(payload)},
                    files=multipart,
                )
            else:
                response = http.post(url, headers=self._headers, json=payload)
        if response.status_code >= 400:
            raise IngestError(response.status_code, response.text)
        return IngestResult.model_validate(response.json())

    def submit_many(self, items: list[NewsSubmission]) -> list[IngestResult]:
        """Send a batch; duplicates are reported per item, not as an error."""

        url = f"{self.base_url}/api/v1/ingest/news/batch"
        body = [n.model_dump(mode="json", exclude_none=True) for n in items]
        with httpx.Client(timeout=self.timeout) as http:
            response = http.post(url, headers=self._headers, json={"items": body})
        if response.status_code >= 400:
            raise IngestError(response.status_code, response.text)
        return [IngestResult.model_validate(r) for r in response.json()["results"]]
