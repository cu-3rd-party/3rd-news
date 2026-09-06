from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable
from typing import Any

from ...domain.entities.candidate import Candidate

MAX_NOISE_LENGTH = 220
BROADCASTER_POSTS = 5
_MARKUP = re.compile("\\*\\*|^#{1,3}\\s|^\\s*[-•]\\s", re.MULTILINE)
_BROADCAST = re.compile("@all\\b|@channel\\b", re.IGNORECASE)


def author_of(item: dict[str, Any]) -> str:
    extra = item.get("extra") or {}
    return str(extra.get("author") or "")


def broadcasters(items: Iterable[dict[str, Any]]) -> set[tuple[str, str]]:
    counts: Counter[tuple[str, str]] = Counter()
    for item in items:
        counts[item.get("source_key") or "", author_of(item)] += 1
    return {pair for pair, count in counts.items() if count >= BROADCASTER_POSTS}


def reasons_to_reject(item: dict[str, Any], regulars: set[tuple[str, str]]) -> tuple[str, ...]:
    body = (item.get("body_md") or "").strip()
    if not body:
        return ("пустой текст",)
    found: list[str] = []
    if len(body) > MAX_NOISE_LENGTH:
        return ()
    found.append(f"короткий ({len(body)} симв.)")
    if _MARKUP.search(body):
        return ()
    if "http" in body:
        return ()
    if _BROADCAST.search(body):
        return ()
    found.append("без разметки, ссылок и @all")
    if (item.get("source_key") or "", author_of(item)) in regulars:
        return ()
    found.append("автор не ведёт этот канал")
    return tuple(found)


def find_candidates(items: list[dict[str, Any]]) -> list[Candidate]:
    regulars = broadcasters(items)
    candidates: list[Candidate] = []
    for item in items:
        reasons = reasons_to_reject(item, regulars)
        if not reasons:
            continue
        candidates.append(
            Candidate(
                id=item["id"],
                source_key=item.get("source_key") or "",
                author=author_of(item),
                text=" ".join((item.get("body_md") or "").split())[:110],
                reasons=reasons,
            )
        )
    return candidates


def describe(candidates: list[Candidate], total: int) -> str:
    by_channel = Counter(candidate.source_key for candidate in candidates)
    lines = [f"постов: {total}", f"кандидатов в rejected: {len(candidates)}", ""]
    for channel, count in by_channel.most_common():
        lines.append(f"  {count:4d}  {channel}")
    lines.append("")
    for candidate in candidates:
        lines.append(f"  {candidate.id[:8]}  {candidate.author or '?':22.22}  «{candidate.text}»")
    return "\n".join(lines)
