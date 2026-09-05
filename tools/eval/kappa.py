"""Второй разметчик работает вслепую по CSV; здесь — выгрузка и согласие.

Соглашения в CSV: пустая ячейка — ось не размечал; `-` — «ось не
применима»; несколько значений — через `;`.
"""

from __future__ import annotations

import csv
import random
from collections import Counter
from pathlib import Path

from thirdnews_contracts import Taxonomy

from .dataset import Record, gold_labels

NONE = "-"
META_COLUMNS = ("id", "source_key", "title", "body_md")


def write_blind_csv(
    records: list[Record], taxonomy: Taxonomy, path: Path, n: int, seed: int
) -> list[str]:
    sample = random.Random(seed).sample(records, k=min(n, len(records)))
    facets = [facet.slug for facet in taxonomy.facets]
    with Path(path).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow([*META_COLUMNS, *facets])
        for record in sample:
            writer.writerow(
                [
                    record.id,
                    record.source_key or "",
                    record.title or "",
                    record.body_md,
                    *([""] * len(facets)),
                ]
            )
    return [record.id for record in sample]


def _parse_cell(cell: str | None) -> set[str] | None:
    cell = (cell or "").strip()
    if not cell:
        return None
    if cell == NONE:
        return set()
    return {part.strip() for part in cell.split(";") if part.strip()}


def read_labels_csv(path: Path) -> dict[str, dict[str, set[str] | None]]:
    result: dict[str, dict[str, set[str] | None]] = {}
    with Path(path).open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            result[row["id"]] = {
                key: _parse_cell(value) for key, value in row.items() if key not in META_COLUMNS
            }
    return result


def cohen_kappa(a: list[str], b: list[str]) -> float:
    if len(a) != len(b) or not a:
        raise ValueError("нужны две одинаковые по длине непустые последовательности")
    n = len(a)
    observed = sum(1 for x, y in zip(a, b) if x == y) / n
    count_a, count_b = Counter(a), Counter(b)
    expected = sum(count_a[c] * count_b.get(c, 0) for c in count_a) / (n * n)
    if expected == 1.0:
        # Оба всегда ставили одно и то же — согласие полное, формула даёт 0/0.
        return 1.0
    return (observed - expected) / (1 - expected)


def _category(labels: set[str]) -> str:
    return ";".join(sorted(labels)) if labels else NONE


def kappa_report(
    records: list[Record], other: dict[str, dict[str, set[str] | None]], taxonomy: Taxonomy
) -> dict:
    by_id = {record.id: record for record in records}
    report: dict[str, dict] = {}
    for facet in taxonomy.facets:
        pairs: list[tuple[str, set[str], set[str]]] = []
        for record_id, facets in other.items():
            record = by_id.get(record_id)
            if record is None:
                continue
            gold = gold_labels(record, facet.slug)
            theirs = facets.get(facet.slug)
            if gold is None or theirs is None:
                continue
            pairs.append((record_id, gold, theirs))

        if not pairs:
            report[facet.slug] = {"n": 0, "kappa": None, "disagreements": []}
            continue

        if facet.type.value == "single":
            kappa = cohen_kappa(
                [_category(g) for _, g, _ in pairs], [_category(t) for _, _, t in pairs]
            )
        else:
            # Для multi-оси — каппа по каждому значению как по бинарному
            # признаку, среднее по значениям, которые кто-то хоть раз ставил.
            per_value = []
            for value in facet.values:
                a = ["1" if value.slug in g else "0" for _, g, _ in pairs]
                b = ["1" if value.slug in t else "0" for _, _, t in pairs]
                if set(a) | set(b) == {"0"}:
                    continue
                per_value.append(cohen_kappa(a, b))
            kappa = sum(per_value) / len(per_value) if per_value else 1.0

        report[facet.slug] = {
            "n": len(pairs),
            "kappa": kappa,
            "disagreements": [
                {"id": record_id, "gold": sorted(g), "other": sorted(t)}
                for record_id, g, t in pairs
                if g != t
            ],
        }
    return report
