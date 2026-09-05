"""Какие оси размечает человек, а какие приходят от источника."""

from __future__ import annotations

import json
from typing import Any

from tools.taxonomy.apply import TAXONOMY_PATH


def source_driven(sources: list[dict[str, Any]]) -> set[str]:
    """Оси из `default_labels` каналов — их человек не ставит."""

    return {key for source in sources for key in (source.get("default_labels") or {})}


def human_facets(driven: set[str]) -> list[str]:
    facets = json.loads(TAXONOMY_PATH.read_text(encoding="utf-8"))["facets"]
    return [facet["slug"] for facet in facets if facet["slug"] not in driven]


def labelled(item: dict[str, Any], facets: list[str]) -> set[str]:
    """Оси, которые человек проставил руками (метки источника не в счёт)."""

    return {facet for facet in (item.get("manual_facets") or []) if facet in facets}
