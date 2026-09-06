from __future__ import annotations

import asyncio
import uuid

from lib.core.config import SEARCH_FILTERABLE, SEARCH_SORTABLE, Settings
from lib.infra.clients.search.client import MeiliSearchClient


async def documents():
    yield {
        "id": "qa-visible",
        "title": "Visible QA record",
        "body": "search contract",
        "source_text": "qa",
        "source": ["qa-source"],
        "source_ids": [str(uuid.uuid4())],
        "has_attachments": False,
        "published_at_ts": 2,
        "received_at_ts": 1,
        "language": "en",
        "published_at": "2026-01-01T00:00:00+00:00",
        "status": "published",
        "urgency": 0,
        "impact": 0,
        "editorial_priority": 0,
        "importance": 0,
        "facets": {"category": ["qa"]},
        "revision": 1,
        "visibility_revision": 1,
    }
    yield {
        "id": "qa-hidden",
        "title": "Hidden QA record",
        "body": "search contract",
        "source_text": "qa",
        "source": ["other-source"],
        "source_ids": [str(uuid.uuid4())],
        "has_attachments": False,
        "published_at_ts": 1,
        "received_at_ts": 1,
        "language": "en",
        "published_at": "2026-01-01T00:00:00+00:00",
        "status": "draft",
        "urgency": 0,
        "impact": 0,
        "editorial_priority": 0,
        "importance": 0,
        "facets": {"category": ["qa"]},
        "revision": 1,
        "visibility_revision": 2,
    }


async def exercise() -> tuple[int, list[str], int]:
    settings = Settings()
    index = f"qa-reindex-{uuid.uuid4().hex}"
    client = MeiliSearchClient(
        settings.search_url,
        settings.search_key_value,
        index=index,
        timeout_seconds=settings.search_task_timeout_seconds,
    )
    try:
        assert await client.health()
        count = await client.replace_all(
            documents(),
            batch_size=1,
            filterable=SEARCH_FILTERABLE,
            sortable=SEARCH_SORTABLE,
        )
        result = await client.search(
            "",
            filters=['status = "published"', 'source IN ["qa-source"]'],
            facets=("source", "facets.category"),
            sort=("published_at_ts:desc",),
        )
        hit_ids = [str(hit["id"]) for hit in result["hits"]]
        source_count = int(result["facetDistribution"]["source"]["qa-source"])
        assert count == 2
        assert hit_ids == ["qa-visible"]
        assert source_count == 1
        return count, hit_ids, source_count
    finally:
        try:
            deletion = await client._request("DELETE", f"/indexes/{index}")
            await client.wait_task(int(deletion["taskUid"]))
        finally:
            await client.close()


if __name__ == "__main__":
    indexed, hits, facet_count = asyncio.run(exercise())
    print(f"Meilisearch reindex={indexed}; hits={hits}; source facet={facet_count}")
