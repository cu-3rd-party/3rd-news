from __future__ import annotations

import asyncio
from typing import Any, cast

import pytest
from lib.infra.clients.search.indexer import SearchIndexer


class SettingsRecorder:
    def __init__(self) -> None:
        self.index = "qa-news"
        self.filterable: tuple[str, ...] = ()
        self.sortable: tuple[str, ...] = ()

    async def ensure_index(self) -> None:
        return None

    async def configure(self, *, filterable, sortable) -> None:
        self.filterable = tuple(filterable)
        self.sortable = tuple(sortable)


@pytest.mark.asyncio
async def test_index_configuration_supports_every_feed_filter_and_sort() -> None:
    search = SettingsRecorder()
    worker = SearchIndexer(cast(Any, None), cast(Any, search), owner="qa")
    stop = asyncio.Event()
    stop.set()

    await worker.run(stop=stop)

    assert {"status", "facets", "source", "visibility_revision"} <= set(search.filterable)
    assert {
        "published_at",
        "importance",
        "urgency",
        "impact",
        "editorial_priority",
    } <= set(search.sortable)
