from __future__ import annotations

from typing import Any


def pinned(items: list[dict[str, Any]], facet: str) -> list[dict[str, Any]]:
    return [item for item in items if facet in (item.get("manual_facets") or [])]


def describe(items: list[dict[str, Any]], facet: str) -> str:
    if not items:
        return f"ручных меток по оси «{facet}» нет"
    lines = [f"ручная метка по оси «{facet}» стоит у {len(items)} постов:", ""]
    for item in items:
        values = ", ".join((item.get("effective") or {}).get(facet, [])) or "—"
        title = " ".join((item.get("title") or "").split())[:50] or "(без заголовка)"
        lines.append(
            f"  {item['id'][:8]}  {item.get('source_key', ''):45.45}  {values:20.20}  {title}"
        )
    return "\n".join(lines)
