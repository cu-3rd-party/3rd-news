from __future__ import annotations

import json
from typing import Any

from .apply_taxonomy import TAXONOMY_PATH


def source_driven(sources: list[dict[str, Any]]) -> set[str]:
    return {key for source in sources for key in source.get("default_labels") or {}}


def human_facets(driven: set[str]) -> list[str]:
    facets = json.loads(TAXONOMY_PATH.read_text(encoding="utf-8"))["facets"]
    return [facet["slug"] for facet in facets if facet["slug"] not in driven]


def labelled(item: dict[str, Any], facets: list[str]) -> set[str]:
    return {facet for facet in item.get("manual_facets") or [] if facet in facets}
