from __future__ import annotations

from typing import Any, cast
from unittest.mock import Mock

import pytest
from tools.lib.infra.clients.admin import Admin
from tools.lib.interactor.use_cases.apply_taxonomy import (
    _facet_wire,
    _normalize_facets,
    _normalize_sources,
    _source_wire,
    _value_wire,
)


def _client() -> Any:
    paths: list[str] = []
    client = Mock()
    client.paths = paths

    def post(path: str, **_kwargs: Any) -> Any:
        paths.append(path)
        response = Mock()
        response.raise_for_status.return_value = None
        return response

    client.post.side_effect = post
    return client


def test_taxonomy_wire_maps_legacy_ui_names_to_v2() -> None:
    assert _facet_wire({"slug": "topic", "title": "Topic", "type": "multi"})["kind"] == "multi"
    assert _value_wire({"slug": "event", "title": "Event", "is_active": False})["enabled"] is False
    assert _source_wire({"slug": "rss", "title": "RSS", "is_active": False})["enabled"] is False


def test_collection_normalization_restores_tool_model() -> None:
    facets = _normalize_facets(
        [{"slug": "topic", "kind": "single", "enabled": True, "values": [{"enabled": False}]}]
    )
    assert facets[0]["type"] == "single"
    assert facets[0]["values"][0]["is_active"] is False
    assert _normalize_sources([{"slug": "rss", "enabled": False}])[0]["is_active"] is False


def test_status_uses_v2_transition_routes() -> None:
    client = _client()
    admin = Admin(cast(Any, client))
    admin.set_status("n1", "published")
    admin.set_status("n2", "rejected")
    assert client.paths == [
        "/api/v1/admin/news/n1/publish",
        "/api/v1/admin/news/n2/reject",
    ]


def test_status_rejects_unsupported_transition() -> None:
    with pytest.raises(ValueError):
        Admin(cast(Any, _client())).set_status("n", "draft")
