from __future__ import annotations

import asyncio
from typing import Any, cast

import pytest
from lib.infra.clients.search.client import SearchNotReady
from lib.infra.clients.search.indexer import SearchIndexer
from lib.infra.storage.postgres.models import News, NewsVersion, SearchProjection

from .fakes.blocking_replacement_client import BlockingReplacementClient
from .fakes.recording_replacement_client import RecordingReplacementClient

pytestmark = pytest.mark.integration


async def test_visibility_change_during_reindex_stays_fail_closed(
    integration_database,
) -> None:
    news = News(status="published", revision=1, visibility_revision=1)
    version = NewsVersion(news=news, number=1, body_md="Visible before policy change")
    async with integration_database() as session:
        session.add_all([news, version])
        await session.flush()
        news.current_version_id = version.id
        session.add(
            SearchProjection(
                news_id=news.id,
                desired_revision=1,
                indexed_revision=1,
                visibility_revision=1,
                status="ready",
            )
        )
        await session.commit()
        news_id = news.id

    client = BlockingReplacementClient()
    indexer = SearchIndexer(integration_database, cast(Any, client), owner="qa-reindex")
    rebuild = asyncio.create_task(indexer.reindex_all(page_size=500))
    try:
        await asyncio.wait_for(client.started.wait(), timeout=15)
        snapshot = next(document for document in client.documents if document["id"] == str(news_id))
        assert snapshot["revision"] == 1

        async with integration_database() as session, session.begin():
            changed = await session.get(News, news_id, with_for_update=True)
            projection = await session.get(SearchProjection, news_id, with_for_update=True)
            assert changed is not None and projection is not None
            changed.revision = 2
            changed.visibility_revision = 2
            projection.desired_revision = 2
    finally:
        client.release.set()

    assert await asyncio.wait_for(rebuild, timeout=15) == len(client.documents)

    async with integration_database() as session:
        projection = await session.get(SearchProjection, news_id)
        assert projection is not None
        assert projection.indexed_revision == 1
        assert projection.visibility_revision == 1
        assert projection.desired_revision == 2
        assert projection.status == "pending"
    with pytest.raises(SearchNotReady):
        await indexer.assert_visibility_ready()


async def test_reindex_creates_checkpoint_for_news_without_projection(
    integration_database,
) -> None:
    news = News(status="published", revision=3, visibility_revision=2)
    version = NewsVersion(news=news, number=1, body_md="Never incrementally indexed")
    async with integration_database() as session:
        session.add_all([news, version])
        await session.flush()
        news.current_version_id = version.id
        await session.commit()
        news_id = news.id

    async with integration_database() as session:
        assert await session.get(SearchProjection, news_id) is None

    client = RecordingReplacementClient()
    indexer = SearchIndexer(integration_database, cast(Any, client), owner="qa-fresh-projection")
    count = await indexer.reindex_all(page_size=2)

    assert count == len(client.documents)
    assert any(document["id"] == str(news_id) for document in client.documents)
    async with integration_database() as session:
        projection = await session.get(SearchProjection, news_id)
        assert projection is not None
        assert projection.desired_revision == 3
        assert projection.indexed_revision == 3
        assert projection.visibility_revision == 2
        assert projection.status == "ready"
