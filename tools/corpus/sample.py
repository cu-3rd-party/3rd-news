"""Отбирает посты в золотой набор с квотой на канал.

Без квоты набор перекосит `town-square`: в нём каждое пятое объявление — «этаж
закрыт под мероприятие», и модель научится угадывать именно их. Квота
пропорциональна размеру канала, но с потолком, поэтому маленькие каналы
(магистратуры, чаты потоков) в набор попадают.

Из отбора выпадают отклонённые посты и копии перепечаток: копии получат
разметку скриптом `copy_labels`, размечать их руками не нужно.

    python -m tools.corpus.sample
    python -m tools.corpus.sample --size 200 --out data/gold_plan.tsv
"""

from __future__ import annotations

import argparse
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from tools.corpus.client import Admin, add_connection_args, credentials
from tools.corpus.duplicates import DEFAULT_THRESHOLD, find_groups
from tools.corpus.copy_labels import to_post
from tools.corpus.facets import human_facets, labelled, source_driven

#: Доля набора, больше которой один канал занять не может.
DEFAULT_CAP = 0.2
#: Целевой размер золотого набора.
DEFAULT_SIZE = 200


def quotas(sizes: dict[str, int], size: int, cap: float = DEFAULT_CAP) -> dict[str, int]:
    """Сколько постов взять из каждого канала.

    Пропорция от размера канала, но не больше `cap` от набора. Потолок нужен
    против доминирования одного канала, а не для урезания набора: если каналов
    мало и при потолке нужный размер недостижим, потолок поднимается — иначе
    запрошенные 300 превратились бы в 60 молча.
    """

    total = sum(sizes.values())
    if total == 0 or size <= 0:
        return {}
    size = min(size, total)

    ceiling = max(1, int(size * cap))
    largest = max(sizes.values())
    while ceiling < largest and sum(min(ceiling, count) for count in sizes.values()) < size:
        ceiling += 1

    share = {key: min(ceiling, count, round(size * count / total)) for key, count in sizes.items()}
    # Округление вниз и потолок всегда недодают несколько штук — раздаём остаток
    # по кругу, начиная с самых больших каналов.
    order = sorted(sizes, key=lambda key: (-sizes[key], key))
    while sum(share.values()) < size:
        moved = False
        for key in order:
            if sum(share.values()) >= size:
                break
            if share[key] < min(ceiling, sizes[key]):
                share[key] += 1
                moved = True
        if not moved:  # все каналы исчерпаны
            break
    return {key: value for key, value in share.items() if value}


def candidates(items: list[dict[str, Any]], threshold: float = DEFAULT_THRESHOLD) -> list[dict[str, Any]]:
    """Посты, которые имеет смысл размечать руками."""

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
    """Отбирает набор, удерживая в нём уже размеченное.

    `keep` — id, которые обязаны попасть в план: разметка стоит человеко-часов,
    и менять размер набора не значит выбрасывать сделанное. Они занимают места
    в квоте своего канала, остальное добирается случайно.
    """

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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    add_connection_args(parser)
    parser.add_argument("--size", type=int, default=DEFAULT_SIZE)
    parser.add_argument("--cap", type=float, default=DEFAULT_CAP, help="потолок доли одного канала")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    parser.add_argument("--out", type=Path, help="куда записать TSV «id / канал / дата / заголовок»")
    parser.add_argument(
        "--fresh", action="store_true", help="не удерживать уже размеченное в плане"
    )
    args = parser.parse_args(argv)

    creds = credentials(args)
    if creds is None:
        print("нужны --email/--password (или BOOTSTRAP_ADMIN_* в окружении)", file=sys.stderr)
        return 2

    with Admin.connect(args.base_url, *creds) as admin:
        items = list(admin.news())
        sources = admin.client.get("/api/v1/admin/sources").json()

    pool = candidates(items, args.threshold)
    keep: frozenset[str] = frozenset()
    if not args.fresh:
        facets = human_facets(source_driven(sources))
        keep = frozenset(
            item["id"] for item in pool if labelled(item, facets) == set(facets)
        )
    chosen = pick(pool, args.size, args.seed, args.cap, keep)
    print(describe(chosen, len(pool), len(items), len(keep)))

    if args.out:
        rows = ["id\tsource_key\tpublished_at\ttitle"]
        for item in chosen:
            title = " ".join((item.get("title") or "").split())[:80]
            rows.append(
                "\t".join(
                    [
                        item["id"],
                        item.get("source_key") or "",
                        (item.get("published_at") or "")[:10],
                        title,
                    ]
                )
            )
        args.out.write_text("\n".join(rows) + "\n", encoding="utf-8")
        print(f"\nсписок записан в {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
