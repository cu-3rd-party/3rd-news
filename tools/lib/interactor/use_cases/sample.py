from __future__ import annotations

import random
from collections import Counter, defaultdict
from typing import Any

from .copy_labels import to_post
from .duplicates import DEFAULT_THRESHOLD, find_groups

DEFAULT_CAP = 0.2
DEFAULT_SIZE = 200


def quotas(sizes: dict[str, int], size: int, cap: float = DEFAULT_CAP) -> dict[str, int]:
    total = sum(sizes.values())
    if total == 0 or size <= 0:
        return {}
    size = min(size, total)
    ceiling = max(1, int(size * cap))
    largest = max(sizes.values())
    while ceiling < largest and sum(min(ceiling, count) for count in sizes.values()) < size:
        ceiling += 1
    share = {key: min(ceiling, count, round(size * count / total)) for key, count in sizes.items()}
    order = sorted(sizes, key=lambda key: (-sizes[key], key))
    while sum(share.values()) < size:
        moved = False
        for key in order:
            if sum(share.values()) >= size:
                break
            if share[key] < min(ceiling, sizes[key]):
                share[key] += 1
                moved = True
        if not moved:
            break
    return {key: value for key, value in share.items() if value}


def candidates(
    items: list[dict[str, Any]], threshold: float = DEFAULT_THRESHOLD
) -> list[dict[str, Any]]:
    alive = [item for item in items if item.get("status") != "rejected"]
    copies = {
        post.id
        for group in find_groups([to_post(item) for item in alive], threshold)
        for post, _ in group.copies
    }
    return [item for item in alive if item["id"] not in copies]


def pick(
    items: list[dict[str, Any]],
    size: int,
    seed: int,
    cap: float = DEFAULT_CAP,
    keep: frozenset[str] = frozenset(),
) -> list[dict[str, Any]]:
    by_channel: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        by_channel[item.get("source_key") or ""].append(item)
    share = quotas({key: len(value) for key, value in by_channel.items()}, size, cap)
    kept = [item for item in items if item["id"] in keep]
    kept_by_channel = Counter(item.get("source_key") or "" for item in kept)
    rng = random.Random(seed)
    chosen: list[dict[str, Any]] = list(kept)
    for channel, count in share.items():
        need = count - kept_by_channel.get(channel, 0)
        if need <= 0:
            continue
        pool = sorted(
            (item for item in by_channel[channel] if item["id"] not in keep),
            key=lambda item: item["id"],
        )
        chosen.extend(rng.sample(pool, min(need, len(pool))))
    chosen.sort(key=lambda item: (item.get("source_key") or "", item.get("published_at") or ""))
    return chosen


def describe(chosen: list[dict[str, Any]], pool: int, total: int, kept: int = 0) -> str:
    by_channel = Counter(item.get("source_key") or "" for item in chosen)
    lines = [
        f"всего постов: {total}",
        f"кандидатов (без отклонённых и копий): {pool}",
        f"отобрано: {len(chosen)} (из них уже размечено: {kept})",
        "",
        "сколько размечать в каждом канале:",
    ]
    for channel, count in by_channel.most_common():
        lines.append(f"  {count:4d}  {channel}")
    return "\n".join(lines)
