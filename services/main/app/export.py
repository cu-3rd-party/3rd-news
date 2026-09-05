"""Экспорт ручной разметки в JSONL — сырьё для измерителя `tools/eval`.

Одна строка на новость. Уходят только ручные метки: измеритель сравнивает
классификаторы с человеком, а не с самими собой. Файлы вложений остаются на
томе `media`; в записи — относительный путь, чтобы измеритель мог их
прочитать, когда дойдёт до картинок.
"""

from __future__ import annotations

from .models import News

#: Отклонённое — не новость (опрос, «спасибо всем»), в набор не идёт.
EXPORT_STATUSES = ("pending", "needs_review", "classified", "published", "archived")


def export_record(news: News) -> dict:
    labels: dict[str, list[str]] = {}
    for label in news.labels:
        if label.origin != "manual":
            continue
        labels.setdefault(label.facet.slug, []).append(label.value.slug)
    # Ось из manual_facets без единой метки тоже должна присутствовать:
    # «редактор решил, что не применима» — это ответ, а не пропуск.
    for facet_slug in news.manual_facets or []:
        labels.setdefault(facet_slug, [])

    return {
        "id": str(news.id),
        "source_key": news.source.slug if news.source else None,
        "title": news.title,
        "body_md": news.body_md,
        "source_link": news.source_link,
        "source_text": news.source_text,
        "published_at": news.published_at.isoformat() if news.published_at else None,
        "received_at": news.received_at.isoformat() if news.received_at else None,
        "status": news.status,
        "attachments": [
            {
                "kind": item.kind,
                "path": item.storage_path,
                "mime": item.mime,
                "filename": item.filename,
                "caption": item.caption,
            }
            for item in news.attachments
        ],
        "extra": news.extra or {},
        "labels": {slug: sorted(values) for slug, values in sorted(labels.items())},
        "manual_facets": sorted(news.manual_facets or []),
        "is_gold": bool(news.is_gold),
    }
