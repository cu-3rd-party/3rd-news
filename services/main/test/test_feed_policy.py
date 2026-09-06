from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest
from fastapi import HTTPException
from lib.handlers.feed import feed
from lib.handlers.media import router as media_router
from lib.infra.clients.auth import Principal
from starlette.datastructures import QueryParams

from .fakes.feed_session import FeedSession
from .fakes.recording_search import RecordingSearch


def request_with(query: list[tuple[str, str]], search: RecordingSearch):
    return SimpleNamespace(
        query_params=QueryParams(query),
        app=SimpleNamespace(state=SimpleNamespace(search=search)),
    )


@pytest.mark.asyncio
async def test_feed_preset_cannot_be_widened_by_query_parameters() -> None:
    search = RecordingSearch()
    request = request_with([("facet.topic", "untrusted"), ("source", "untrusted-source")], search)
    principal = Principal(
        "api_key",
        "qa-key",
        "QA key",
        frozenset({"read"}),
        filter_preset={"facets": {"topic": ["official"]}, "sources": ["trusted-source"]},
    )

    result = await feed(
        cast(Any, request),
        cast(Any, FeedSession()),
        principal,
        q="deadline",
        limit=20,
        cursor=None,
    )

    assert result["items"] == []
    assert result["total"] == 0
    assert search.kwargs == {}


@pytest.mark.asyncio
async def test_feed_applies_allowed_preset_values_to_search() -> None:
    search = RecordingSearch()
    request = request_with([("facet.topic", "official")], search)
    principal = Principal(
        "api_key",
        "qa-key",
        "QA key",
        frozenset({"read"}),
        filter_preset={"facets": {"topic": ["official"]}, "sources": ["trusted-source"]},
    )
    await feed(
        cast(Any, request),
        cast(Any, FeedSession()),
        principal,
        q="deadline",
        source=None,
        published_from=None,
        published_to=None,
        received_from=None,
        received_to=None,
        has_attachments=None,
        order="desc",
        sort_by="published_at",
        limit=20,
        cursor=None,
    )

    filters = search.kwargs["filters"]
    assert 'source IN ["trusted-source"]' in filters
    assert 'facets.topic IN ["official"]' in filters


@pytest.mark.asyncio
async def test_feed_rejects_malformed_cursor_before_search() -> None:
    search = RecordingSearch()
    principal = Principal("api_key", "qa-key", "QA key", frozenset({"read"}))
    with pytest.raises(HTTPException) as raised:
        await feed(
            cast(Any, request_with([], search)),
            cast(Any, FeedSession()),
            principal,
            q=None,
            limit=20,
            cursor="not-an-offset",
        )
    assert raised.value.status_code == 400
    assert search.kwargs == {}


def test_media_routes_have_read_auth_dependency() -> None:
    media_routes = [
        cast(Any, route)
        for route in media_router.routes
        if getattr(route, "path", None) == "/api/v1/media/{attachment_id}"
    ]
    assert {method for route in media_routes for method in route.methods} == {"GET", "HEAD"}
    assert all(route.dependant.dependencies for route in media_routes)
