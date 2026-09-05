"""Показывает и снимает флаг `is_gold`.

Золото — это заморозка, а не «проверено»: помеченный пост навсегда исключается
из few-shot примеров классификатора. Ставится он один раз и поздно, после
первых прогонов измерителя, примерно на половину набора. Во время разметки
флаг не нужен, а если его успели наставить — этот скрипт снимает.

    python -m tools.corpus.gold
    python -m tools.corpus.gold --clear --apply
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from typing import Any

from tools.corpus.client import Admin, add_connection_args, credentials

#: Ручка `POST /admin/news/gold` принимает список; шлём частями, чтобы не
#: упереться в размер тела на большом наборе.
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    add_connection_args(parser)
    parser.add_argument("--clear", action="store_true", help="снять флаг со всех золотых")
    parser.add_argument("--apply", action="store_true", help="действительно записать")
    args = parser.parse_args(argv)

    creds = credentials(args)
    if creds is None:
        print("нужны --email/--password (или BOOTSTRAP_ADMIN_* в окружении)", file=sys.stderr)
        return 2

    with Admin.connect(args.base_url, *creds) as admin:
        items = list(admin.news())
        print(describe(items))

        if not args.clear:
            return 0
        ids = [item["id"] for item in golden(items)]
        if not ids:
            return 0
        if not args.apply:
            print(f"\n(снял бы флаг с {len(ids)} постов; чтобы применить — --apply)")
            return 0

        updated = 0
        for start in range(0, len(ids), BATCH):
            updated += admin.set_gold(ids[start : start + BATCH], False)
        print(f"\nснято золото с {updated} постов (разметка не тронута)")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
