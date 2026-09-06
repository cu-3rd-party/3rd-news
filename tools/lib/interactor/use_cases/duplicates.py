from __future__ import annotations

import json
import re
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from ...domain.entities.group import Group
from ...domain.entities.post import Post

DEFAULT_THRESHOLD = 0.8
SHINGLE = 3
_EMOJI_CODE = re.compile(":[a-z0-9_\\-]{3,40}:")
_URL = re.compile("https?://\\S+")
_MENTION = re.compile("@[\\w.\\-]+")
_NON_WORD = re.compile("[^\\w\\s]+", re.UNICODE)
_SPACE = re.compile("\\s+")
_MONTHS = {
    "январ": 1,
    "феврал": 2,
    "март": 3,
    "апрел": 4,
    "ма": 5,
    "июн": 6,
    "июл": 7,
    "август": 8,
    "сентябр": 9,
    "октябр": 10,
    "ноябр": 11,
    "декабр": 12,
}
_DAY_MONTH = re.compile(
    "\\b(\\d{1,2})\\s*(январ|феврал|март|апрел|мая|май|июн|июл|август|сентябр|октябр|ноябр|декабр)",
    re.IGNORECASE,
)
_NUMERIC_DATE = re.compile("\\b(\\d{1,2})[.](\\d{1,2})(?:[.]\\d{2,4})?\\b")
_DAY_RANGE = re.compile(
    "\\b(\\d{1,2})\\s*(?:на|по|и|-|–|—)\\s*(\\d{1,2})\\s*(январ|феврал|март|апрел|мая|май|июн|июл|август|сентябр|октябр|ноябр|декабр)",
    re.IGNORECASE,
)


def _month_number(month: str) -> int | None:
    stem = month.lower().rstrip("яй")
    return _MONTHS.get(stem) or _MONTHS.get(stem[:5]) or _MONTHS.get(stem[:2])


def event_dates(text: str | None) -> frozenset[tuple[int, int]]:
    found: set[tuple[int, int]] = set()
    for first, _, month in _DAY_RANGE.findall(text or ""):
        number = _month_number(month)
        if number and 1 <= int(first) <= 31:
            found.add((int(first), number))
    for day, month in _DAY_MONTH.findall(text or ""):
        number = _month_number(month)
        if number and 1 <= int(day) <= 31:
            found.add((int(day), number))
    for day, month in _NUMERIC_DATE.findall(text or ""):
        if 1 <= int(day) <= 31 and 1 <= int(month) <= 12:
            found.add((int(day), int(month)))
    return frozenset(found)


def same_event(left: frozenset[tuple[int, int]], right: frozenset[tuple[int, int]]) -> bool:
    if not left or not right:
        return True
    return bool(left & right)


def normalize(text: str | None) -> str:
    value = _EMOJI_CODE.sub(" ", text or "")
    value = _URL.sub(" ", value)
    value = _MENTION.sub(" ", value)
    value = _NON_WORD.sub(" ", value)
    return _SPACE.sub(" ", value).strip().lower()


def shingles(text: str, size: int = SHINGLE) -> frozenset[str]:
    words = normalize(text).split()
    if len(words) < size:
        return frozenset(words)
    return frozenset(" ".join(words[i : i + size]) for i in range(len(words) - size + 1))


def similarity(left: frozenset[str], right: frozenset[str]) -> float:
    if not left or not right:
        return 0.0
    union = len(left | right)
    return len(left & right) / union if union else 0.0


def load_posts(path: Path) -> list[Post]:
    posts: list[Post] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            posts.append(from_record(json.loads(line)))
    return posts


def from_record(record: dict[str, Any]) -> Post:
    title = (record.get("title") or "").strip()
    if title == "None":
        title = ""
    body = record.get("body_md") or ""
    return Post(
        id=record["id"],
        source_key=record.get("source_key") or "",
        published_at=record.get("published_at") or "",
        text=f"{title}\n{body}".strip(),
    )


def _candidates(index: dict[str, list[int]], own: Iterable[str], position: int) -> set[int]:
    found: set[int] = set()
    for shingle in own:
        found.update(other for other in index.get(shingle, ()) if other < position)
    return found


def find_groups(posts: list[Post], threshold: float = DEFAULT_THRESHOLD) -> list[Group]:
    fingerprints = [shingles(post.text) for post in posts]
    dates = [event_dates(post.text) for post in posts]
    parent = list(range(len(posts)))

    def root(node: int) -> int:
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    index: dict[str, list[int]] = defaultdict(list)
    best: dict[int, float] = {}
    for position, own in enumerate(fingerprints):
        if not own:
            continue
        for other in _candidates(index, own, position):
            score = similarity(own, fingerprints[other])
            if score < threshold or not same_event(dates[position], dates[other]):
                continue
            best[position] = max(best.get(position, 0.0), score)
            best[other] = max(best.get(other, 0.0), score)
            left, right = (root(position), root(other))
            if left != right:
                parent[left] = right
        for shingle in own:
            index[shingle].append(position)
    clusters: dict[int, list[int]] = defaultdict(list)
    for position in range(len(posts)):
        if fingerprints[position]:
            clusters[root(position)].append(position)
    groups: list[Group] = []
    for members in clusters.values():
        if len(members) < 2:
            continue
        members.sort(key=lambda position: (posts[position].published_at, posts[position].id))
        origin, *rest = members
        groups.append(
            Group(
                origin=posts[origin],
                copies=[(posts[position], best.get(position, 0.0)) for position in rest],
            )
        )
    groups.sort(key=lambda group: (-len(group.copies), group.origin.published_at))
    return groups


def copy_pairs(groups: list[Group]) -> list[tuple[str, str, str]]:
    return [
        (post.id, group.origin.id, post.source_key) for group in groups for post, _ in group.copies
    ]


def summarize(groups: list[Group], total: int) -> str:
    copies = sum(len(group.copies) for group in groups)
    return f"постов: {total}\nгрупп перепечаток: {len(groups)}\nкопий, чья разметка копируется: {copies} (вручную размечать {total - copies}, в наборе остаются все {total})"


def describe(groups: list[Group], total: int) -> str:
    lines = [summarize(groups, total)]
    for group in groups:
        head = group.origin.text.split("\n")[0][:70].replace("\n", " ")
        lines.append("")
        lines.append(f"— «{head}»  каналов: {len(group.channels)}")
        lines.append(
            f"    размечаем {group.origin.id}  {group.origin.published_at[:10]}  {group.origin.source_key}"
        )
        for post, score in group.copies:
            lines.append(
                f"    копия     {post.id}  {post.published_at[:10]}  {post.source_key}  ~{score:.2f}"
            )
    return "\n".join(lines)
