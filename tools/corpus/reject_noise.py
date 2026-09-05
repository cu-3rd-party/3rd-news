"""Помечает реплики в чатах курсов как `rejected`, чтобы не размечать их руками.

В чатах дисциплин расширенные права у всех, поэтому парсер приносит не только
объявления кураторов, но и вопросы студентов («зал сегодня работает?»). Метки
им не нужны, а из экспорта золотого набора `rejected` выпадает.

Скрипт ничего не решает за человека: по умолчанию он печатает кандидатов с
началом текста, и только `--apply` меняет статусы. Список применённых id
пишется в `--out`, чтобы отмену можно было собрать обратно.

    python -m tools.corpus.reject_noise
    python -m tools.corpus.reject_noise --out data/rejected.txt --apply
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from tools.corpus.client import Admin, add_connection_args, credentials

#: Длиннее этого — уже не реплика, а объявление, даже без разметки.
MAX_NOISE_LENGTH = 220
#: Автор, у которого в канале столько постов и больше, считается «вещающим»:
#: куратором, преподавателем или ассистентом.
BROADCASTER_POSTS = 5

_MARKUP = re.compile(r"\*\*|^#{1,3}\s|^\s*[-•]\s", re.MULTILINE)
_BROADCAST = re.compile(r"@all\b|@channel\b", re.IGNORECASE)


@dataclass(frozen=True)
class Candidate:
    id: str
    source_key: str
    author: str
    text: str
    reasons: tuple[str, ...]


def author_of(item: dict[str, Any]) -> str:
    extra = item.get("extra") or {}
    return str(extra.get("author") or "")


def broadcasters(items: Iterable[dict[str, Any]]) -> set[tuple[str, str]]:
    """Пары (канал, автор), которые в этом канале публикуют регулярно."""

    counts: Counter[tuple[str, str]] = Counter()
    for item in items:
        counts[(item.get("source_key") or "", author_of(item))] += 1
    return {pair for pair, count in counts.items() if count >= BROADCASTER_POSTS}


def reasons_to_reject(item: dict[str, Any], regulars: set[tuple[str, str]]) -> tuple[str, ...]:
    """Почему это похоже на реплику. Пусто — значит не похоже.

    Требуем совпадения всех признаков сразу: пропустить чужой вопрос в наборе
    дешевле, чем выкинуть настоящее объявление.
    """

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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    add_connection_args(parser)
    parser.add_argument("--status", default="published", help="какие статусы просматривать")
    parser.add_argument("--out", type=Path, help="куда записать применённые id")
    parser.add_argument("--apply", action="store_true", help="действительно поменять статусы")
    args = parser.parse_args(argv)

    creds = credentials(args)
    if creds is None:
        print("нужны --email/--password (или BOOTSTRAP_ADMIN_* в окружении)", file=sys.stderr)
        return 2

    with Admin.connect(args.base_url, *creds) as admin:
        items = list(admin.news(status=args.status))
        candidates = find_candidates(items)
        print(describe(candidates, len(items)))

        if not args.apply:
            print("\n(это только список; чтобы применить — --apply)")
            return 0

        for candidate in candidates:
            admin.set_status(candidate.id, "rejected")
        print(f"\nотклонено: {len(candidates)}")

    if args.out:
        args.out.write_text("\n".join(c.id for c in candidates) + "\n", encoding="utf-8")
        print(f"id записаны в {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
