from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections.abc import AsyncIterable, AsyncIterator, Mapping, Sequence
from typing import Any
from urllib.parse import quote

import aiohttp
from lib.core.config import SEARCH_BATCH_MAX_BYTES
from lib.dto.index_task import IndexTask
from lib.interactor.errors.search import SearchError
from lib.interactor.errors.search_not_ready import SearchNotReady
from lib.interactor.errors.search_task_failed import SearchTaskFailed
from lib.interactor.interfaces.clients.search import SearchClient


class MeiliSearchClient(SearchClient):
    def __init__(
        self,
        url: str,
        api_key: str,
        *,
        index: str = "news-v2",
        timeout_seconds: float = 30.0,
    ) -> None:
        self._url = url.rstrip("/")
        self._key = api_key
        self.index = index
        self._timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        self._session: aiohttp.ClientSession | None = None

    async def health(self) -> bool:
        payload = await self._request("GET", "/health")
        return payload.get("status") == "available"

    async def ready(self) -> None:
        if not await self.health():
            raise SearchNotReady("Meilisearch is not available")

    async def close(self) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None

    async def ensure_index(self, *, uid: str | None = None) -> None:
        selected = uid or self.index
        try:
            await self._request("GET", f"/indexes/{quote(selected, safe='')}")
        except SearchError as exc:
            if "index_not_found" not in str(exc):
                raise
            task = await self._request(
                "POST", "/indexes", json_body={"uid": selected, "primaryKey": "id"}
            )
            await self.wait_task(int(task["taskUid"]))

    async def configure(
        self,
        *,
        uid: str | None = None,
        filterable: Sequence[str] = (),
        sortable: Sequence[str] = (),
        searchable: Sequence[str] = ("title", "body", "source_text"),
    ) -> IndexTask:
        selected = uid or self.index
        payload = await self._request(
            "PATCH",
            f"/indexes/{quote(selected, safe='')}/settings",
            json_body={
                "filterableAttributes": list(filterable),
                "sortableAttributes": list(sortable),
                "searchableAttributes": list(searchable),
                "displayedAttributes": ["*"],
            },
        )
        return await self.wait_task(int(payload["taskUid"]))

    async def put_documents(
        self, documents: Sequence[Mapping[str, Any]], *, uid: str | None = None
    ) -> int:
        selected = uid or self.index
        response = await self._request(
            "POST",
            f"/indexes/{quote(selected, safe='')}/documents?primaryKey=id",
            json_body=list(documents),
        )
        return int(response["taskUid"])

    async def delete_documents(self, ids: Sequence[str], *, uid: str | None = None) -> int:
        selected = uid or self.index
        response = await self._request(
            "POST",
            f"/indexes/{quote(selected, safe='')}/documents/delete-batch",
            json_body=list(ids),
        )
        return int(response["taskUid"])

    async def search(
        self,
        query: str,
        *,
        filters: str | Sequence[str] | None = None,
        facets: Sequence[str] = (),
        sort: Sequence[str] = (),
        offset: int = 0,
        limit: int = 20,
    ) -> Mapping[str, Any]:
        body: dict[str, Any] = {
            "q": query,
            "offset": offset,
            "limit": limit,
            "facets": list(facets),
            "sort": list(sort),
        }
        if filters:
            body["filter"] = filters
        return await self._request(
            "POST", f"/indexes/{quote(self.index, safe='')}/search", json_body=body
        )

    async def wait_task(self, task_uid: int, *, timeout_seconds: float | None = None) -> IndexTask:
        limit = self._timeout.total if timeout_seconds is None else timeout_seconds
        deadline = time.monotonic() + float(limit or 30.0)
        delay = 0.025
        while True:
            payload = await self._request("GET", f"/tasks/{task_uid}")
            status = str(payload.get("status"))
            if status == "succeeded":
                return IndexTask(task_uid, status)
            if status in {"failed", "canceled"}:
                error = payload.get("error")
                raise SearchTaskFailed(f"Meilisearch task {task_uid} {status}: {error}")
            if time.monotonic() >= deadline:
                raise TimeoutError(f"Meilisearch task {task_uid} did not finish in time")
            await asyncio.sleep(delay)
            delay = min(delay * 1.6, 0.5)

    async def replace_all(
        self,
        documents: Sequence[Mapping[str, Any]] | AsyncIterable[Mapping[str, Any]],
        *,
        batch_size: int = 500,
        filterable: Sequence[str] = (),
        sortable: Sequence[str] = (),
        searchable: Sequence[str] = ("title", "body", "source_text"),
    ) -> int:

        temporary = f"{self.index}-reindex-{uuid.uuid4().hex}"
        await self.ensure_index(uid=self.index)
        await self.ensure_index(uid=temporary)
        await self.configure(
            uid=temporary,
            filterable=filterable,
            sortable=sortable,
            searchable=searchable,
        )
        try:
            count = 0
            batch: list[Mapping[str, Any]] = []
            batch_bytes = 0
            async for document in self.iter_documents(documents):
                document_bytes = len(json.dumps(document, ensure_ascii=False).encode())
                if batch and batch_bytes + document_bytes > SEARCH_BATCH_MAX_BYTES:
                    await self.wait_task(await self.put_documents(batch, uid=temporary))
                    batch.clear()
                    batch_bytes = 0
                batch.append(document)
                batch_bytes += document_bytes
                count += 1
                if len(batch) >= batch_size:
                    await self.wait_task(await self.put_documents(batch, uid=temporary))
                    batch.clear()
                    batch_bytes = 0
            if batch:
                await self.wait_task(await self.put_documents(batch, uid=temporary))
            swap = await self._request(
                "POST",
                "/swap-indexes",
                json_body=[{"indexes": [self.index, temporary]}],
            )
            await self.wait_task(int(swap["taskUid"]))
            deletion = await self._request("DELETE", f"/indexes/{quote(temporary, safe='')}")
            await self.wait_task(int(deletion["taskUid"]))
            return count
        except Exception:
            try:
                deletion = await self._request("DELETE", f"/indexes/{quote(temporary, safe='')}")
                await self.wait_task(int(deletion["taskUid"]))
            except Exception:
                pass
            raise

    @staticmethod
    async def iter_documents(
        documents: Sequence[Mapping[str, Any]] | AsyncIterable[Mapping[str, Any]],
    ) -> AsyncIterator[Mapping[str, Any]]:
        if isinstance(documents, AsyncIterable):
            async for document in documents:
                yield document
        else:
            for document in documents:
                yield document

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: Mapping[str, Any] | Sequence[Any] | None = None,
    ) -> Mapping[str, Any]:
        headers = {"Accept": "application/json"}
        if self._key:
            headers["Authorization"] = f"Bearer {self._key}"
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=self._timeout, headers=headers)
        async with self._session.request(method, f"{self._url}{path}", json=json_body) as response:
            raw = await response.read()
            try:
                payload = json.loads(raw) if raw else {}
            except ValueError as exc:
                raise SearchError(
                    f"Meilisearch returned non-JSON status {response.status}"
                ) from exc
            if response.status >= 400:
                code = payload.get("code") if isinstance(payload, dict) else None
                message = payload.get("message") if isinstance(payload, dict) else None
                raise SearchError(f"Meilisearch {response.status} {code}: {message}")
            if not isinstance(payload, dict):
                raise SearchError("Meilisearch returned an unexpected response")
            return payload
