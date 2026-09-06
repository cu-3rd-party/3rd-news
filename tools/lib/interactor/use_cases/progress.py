from __future__ import annotations

from collections import Counter
from typing import Any

from .copy_labels import to_post
from .duplicates import DEFAULT_THRESHOLD, find_groups
from .facets import human_facets, labelled, source_driven
from .sample import DEFAULT_SIZE, candidates, pick


def report(
    items: list[dict[str, Any]],
    sources: list[dict[str, Any]],
    size: int = DEFAULT_SIZE,
    seed: int = 1,
    threshold: float = DEFAULT_THRESHOLD,
    by_channel: bool = False,
) -> str:
    facets = human_facets(source_driven(sources))
    alive = [item for item in items if item.get("status") != "rejected"]
    started = [item for item in alive if labelled(item, facets)]
    done = [item for item in alive if labelled(item, facets) == set(facets)]
    gold = [item for item in items if item.get("is_gold")]
    done_ids = {item["id"] for item in done}
    pool = candidates(items, threshold)
    plan = {item["id"] for item in pick(pool, size, seed, keep=frozenset(done_ids))}
    copies = {
        post.id
        for group in find_groups([to_post(item) for item in alive], threshold)
        for post, _ in group.copies
    }
    left = size - len(done_ids)
    lines = [
        f"постов всего: {len(items)} (отклонено: {len(items) - len(alive)})",
        f"размечено полностью: {len(done)} из {size} — {len(done) * 100 // max(size, 1)}%",
        f"начато, но не дозакрыто: {len(started) - len(done)}",
        f"помечено золотом: {len(gold)}",
        "",
        "по осям:",
    ]
    for facet in facets:
        count = sum(1 for item in alive if facet in (item.get("manual_facets") or []))
        lines.append(f"  {count:4d}  {facet}")
    lines += [
        "",
        f"из размеченного попадает в план выборки: {len(done_ids & plan)}",
        f"из размеченного — копии перепечаток: {len(done_ids & copies)} (их разметку мог проставить copy_labels)",
        f"осталось по плану: {len(plan - done_ids)}",
    ]
    if left > 0:
        lines.append(f"при минуте на пост: ещё около {left // 60} ч {left % 60} мин")
    if by_channel and done:
        lines += ["", "размечено по каналам:"]
        for channel, count in Counter(item.get("source_key") or "" for item in done).most_common():
            lines.append(f"  {count:4d}  {channel}")
    return "\n".join(lines)
