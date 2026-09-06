from __future__ import annotations

from typing import Any

from ...domain.entities.post import Post
from ...domain.entities.transfer import Transfer
from .duplicates import DEFAULT_THRESHOLD, find_groups

SOURCE_DRIVEN = {"program"}


def to_post(item: dict[str, Any]) -> Post:
    title = (item.get("title") or "").strip()
    body = item.get("body_md") or ""
    return Post(
        id=item["id"],
        source_key=item.get("source_key") or "",
        published_at=item.get("published_at") or item.get("received_at") or "",
        text=f"{title}\n{body}".strip(),
    )


def manual_labels(item: dict[str, Any]) -> dict[str, list[str]]:
    effective = item.get("effective") or {}
    return {
        facet: list(effective.get(facet, []))
        for facet in item.get("manual_facets") or []
        if facet not in SOURCE_DRIVEN
    }


def plan_transfers(
    items: list[dict[str, Any]], threshold: float = DEFAULT_THRESHOLD
) -> list[Transfer]:
    by_id = {item["id"]: item for item in items}
    groups = find_groups([to_post(item) for item in items], threshold)
    transfers: list[Transfer] = []
    for group in groups:
        origin = by_id[group.origin.id]
        labels = manual_labels(origin)
        if not labels:
            continue
        for post, _ in group.copies:
            target = by_id[post.id]
            already = {
                facet for facet in target.get("manual_facets") or [] if facet not in SOURCE_DRIVEN
            }
            missing = {facet: values for facet, values in labels.items() if facet not in already}
            if not missing:
                continue
            transfers.append(Transfer(origin["id"], target["id"], post.source_key, missing))
    return transfers


def describe(transfers: list[Transfer]) -> str:
    if not transfers:
        return "копировать нечего: у оригиналов нет ручной разметки или копии уже размечены"
    lines = [f"копий к обновлению: {len(transfers)}", ""]
    for transfer in transfers:
        shown = ", ".join(
            (
                f"{facet}={'+'.join(values) or '—'}"
                for facet, values in sorted(transfer.labels.items())
            )
        )
        lines.append(
            f"  {transfer.target_id[:8]} ← {transfer.origin_id[:8]}  {transfer.source_key}"
        )
        lines.append(f"      {shown}")
    return "\n".join(lines)
