"""Переносит ручную разметку с оригинала объявления на его перепечатки.

Одно и то же объявление уходит в каналы нескольких направлений. Содержательные
оси у копий совпадают, поэтому разметчик размечает самый ранний пост группы, а
этот скрипт раскладывает те же значения на остальные. Направление (`program`)
не копируется никогда: оно приходит из канала каждой копии.

Группы считаются по тем же правилам, что в `tools.corpus.duplicates`, но берутся
из живой базы, а не из выгрузки, — чтобы не разъезжаться с тем, что видит
разметчик.

    python -m tools.corpus.copy_labels
    python -m tools.corpus.copy_labels --apply
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from typing import Any

from tools.corpus.client import Admin, add_connection_args, credentials
from tools.corpus.duplicates import DEFAULT_THRESHOLD, Post, find_groups

#: Ось направления приходит из источника; копировать её между каналами — ровно
#: та ошибка, из-за которой копии нельзя было выбрасывать.
SOURCE_DRIVEN = {"program"}


@dataclass(frozen=True)
class Transfer:
    origin_id: str
    target_id: str
    source_key: str
    labels: dict[str, list[str]]


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
    """Только то, что человек проставил руками, без осей от источника."""

    effective = item.get("effective") or {}
    return {
        facet: list(effective.get(facet, []))
        for facet in item.get("manual_facets") or []
        if facet not in SOURCE_DRIVEN
    }


def plan_transfers(
    items: list[dict[str, Any]], threshold: float = DEFAULT_THRESHOLD
) -> list[Transfer]:
    """Что кому скопировать. Уже размеченные вручную копии не трогаем."""

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
            f"{facet}={'+'.join(values) or '—'}" for facet, values in sorted(transfer.labels.items())
        )
        lines.append(f"  {transfer.target_id[:8]} ← {transfer.origin_id[:8]}  {transfer.source_key}")
        lines.append(f"      {shown}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    add_connection_args(parser)
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    parser.add_argument("--gold", action="store_true", help="пометить копии золотыми вслед за оригиналом")
    parser.add_argument("--apply", action="store_true", help="действительно записать метки")
    args = parser.parse_args(argv)

    creds = credentials(args)
    if creds is None:
        print("нужны --email/--password (или BOOTSTRAP_ADMIN_* в окружении)", file=sys.stderr)
        return 2

    with Admin.connect(args.base_url, *creds) as admin:
        items = [item for item in admin.news() if item.get("status") != "rejected"]
        transfers = plan_transfers(items, args.threshold)
        print(describe(transfers))

        if not args.apply or not transfers:
            if transfers:
                print("\n(это только план; чтобы применить — --apply)")
            return 0

        for transfer in transfers:
            admin.set_labels(transfer.target_id, transfer.labels)
        print(f"\nобновлено копий: {len(transfers)}")

        if args.gold:
            golden = {item["id"] for item in items if item.get("is_gold")}
            targets = sorted({t.target_id for t in transfers if t.origin_id in golden})
            if targets:
                print(f"в золото добавлено: {admin.set_gold(targets, True)}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
