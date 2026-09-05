"""Чтение входов измерителя: золотой набор, таксономия, контекст."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from thirdnews_contracts import FacetSchema, FacetValueSchema, Taxonomy


@dataclass(slots=True)
class Record:
    """Одна строка `gold.jsonl` — см. services/main/app/export.py."""

    id: str
    body_md: str
    source_key: str | None = None
    title: str | None = None
    source_text: str | None = None
    source_link: str | None = None
    published_at: datetime | None = None
    attachments: list[dict] = field(default_factory=list)
    extra: dict = field(default_factory=dict)
    labels: dict[str, list[str]] = field(default_factory=dict)
    manual_facets: list[str] = field(default_factory=list)
    is_gold: bool = False

    @property
    def text(self) -> str:
        return f"{self.title}\n{self.body_md}" if self.title else self.body_md


def _parse_dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def load_records(path: Path) -> list[Record]:
    records: list[Record] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        raw = json.loads(line)
        records.append(
            Record(
                id=str(raw["id"]),
                body_md=raw["body_md"],
                source_key=raw.get("source_key"),
                title=raw.get("title"),
                source_text=raw.get("source_text"),
                source_link=raw.get("source_link"),
                published_at=_parse_dt(raw.get("published_at")),
                attachments=list(raw.get("attachments") or []),
                extra=dict(raw.get("extra") or {}),
                labels={k: list(v) for k, v in (raw.get("labels") or {}).items()},
                manual_facets=list(raw.get("manual_facets") or []),
                is_gold=bool(raw.get("is_gold", False)),
            )
        )
    # Без даты публикации порядок «свежести» неизвестен — такие в конец.
    records.sort(
        key=lambda r: (
            r.published_at is None,
            r.published_at.timestamp() if r.published_at else 0.0,
            r.id,
        )
    )
    return records


def gold_labels(record: Record, facet_slug: str) -> set[str] | None:
    """Эталон по оси. `None` — разметчик ось не трогал, метрики по ней не считаем.

    Пустое множество — ответ «ось не применима», и он тоже проверяется.
    """

    if facet_slug not in record.manual_facets:
        return None
    return set(record.labels.get(facet_slug, []))


def load_taxonomy(path: Path) -> Taxonomy:
    """`GET /api/v1/admin/facets` (список) или `{"facets": [...]}`."""

    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    facets_raw = raw["facets"] if isinstance(raw, dict) else raw
    facets: list[FacetSchema] = []
    for item in facets_raw:
        if not item.get("is_active", True):
            continue
        values = [
            FacetValueSchema(
                slug=v["slug"],
                title=v["title"],
                description=v.get("description"),
                ai_hint=v.get("ai_hint"),
                synonyms=list(v.get("synonyms") or []),
                match_patterns=list(v.get("match_patterns") or []),
                position=v.get("position", 0),
            )
            for v in item.get("values", [])
            if v.get("is_active", True)
        ]
        facets.append(
            FacetSchema(
                slug=item["slug"],
                title=item["title"],
                description=item.get("description"),
                ai_hint=item.get("ai_hint"),
                type=item.get("type", "single"),
                required=item.get("required", False),
                position=item.get("position", 0),
                values=values,
            )
        )
    facets.sort(key=lambda f: (f.position, f.slug))
    return Taxonomy(facets=facets)


def load_context(path: Path | None) -> str | None:
    if path is None:
        return None
    text = Path(path).read_text(encoding="utf-8").strip()
    return text or None
