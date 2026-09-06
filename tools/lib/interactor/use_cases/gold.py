from __future__ import annotations

from collections import Counter
from typing import Any

BATCH = 100


def golden(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [item for item in items if item.get("is_gold")]


def describe(items: list[dict[str, Any]]) -> str:
    gold = golden(items)
    if not gold:
        return "золотых постов нет"
    lines = [f"золотых постов: {len(gold)}", "", "по каналам:"]
    for channel, count in Counter(item.get("source_key") or "" for item in gold).most_common():
        lines.append(f"  {count:4d}  {channel}")
    return "\n".join(lines)
