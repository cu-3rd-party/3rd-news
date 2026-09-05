"""База знаний классификаторов: контекст организации и примеры разметки.

Две разные вещи, и обе — «память» системы:

* **Контекст** — то, что редактор пишет один раз: расшифровки сокращений,
  названия потоков, кто такие кураторы. Без него модель видит «ВКР», «поток
  Восток» и «Fundamentals» как незнакомые слова.
* **Примеры** — как размечает человек. Берутся из ручных правок в админке:
  редактор исправил метку, и его решение уезжает следующим классификаторам.
  Это и есть обучение без обучения — чем дольше работает сервис, тем точнее
  примеры. Золотые новости (`is_gold`) в примеры не попадают — это тестовый
  набор для измерения классификаторов.

Ни то, ни другое классификатор использовать не обязан: поля в контракте
необязательные, и сервис, который их игнорирует, остаётся совместимым.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from thirdnews_contracts import LabeledExample

from .config import settings
from .models import News, NewsLabel, Setting

#: Ключ, под которым лежит текст про организацию.
CONTEXT_KEY = "classification_context"

#: Тела примеров обрезаются: модели нужен образец решения, а не весь текст.
EXAMPLE_BODY_CHARS = 700


async def get_context(session: AsyncSession) -> str | None:
    row = (
        await session.execute(select(Setting).where(Setting.key == CONTEXT_KEY))
    ).scalar_one_or_none()
    if row is None:
        return None
    value = (row.value or {}).get("text")
    return value.strip() or None if isinstance(value, str) else None


async def set_context(session: AsyncSession, text: str) -> str:
    row = (
        await session.execute(select(Setting).where(Setting.key == CONTEXT_KEY))
    ).scalar_one_or_none()
    if row is None:
        row = Setting(key=CONTEXT_KEY, value={})
        session.add(row)
    row.value = {"text": text}
    row.updated_at = datetime.now(timezone.utc)
    await session.flush()
    return text


def examples_query(limit: int, exclude_news_id=None):
    """Запрос за свежими ручными разметками — без золотых новостей.

    Золотые новости — тестовый набор для измерения классификаторов. Попав в
    примеры, они превратили бы тест в подсказку, и метрики стали бы врать.
    """

    query = (
        select(News)
        .join(NewsLabel, NewsLabel.news_id == News.id)
        .where(NewsLabel.origin == "manual")
        .where(News.is_gold.is_(False))
        .options(
            selectinload(News.labels).selectinload(NewsLabel.facet),
            selectinload(News.labels).selectinload(NewsLabel.value),
        )
        .order_by(News.updated_at.desc())
        .limit(limit)
    )
    if exclude_news_id is not None:
        query = query.where(News.id != exclude_news_id)
    return query


async def collect_examples(
    session: AsyncSession, limit: int | None = None, exclude_news_id=None
) -> list[LabeledExample]:
    """Свежие новости, размеченные руками, как образцы для классификатора.

    Берём именно ручные метки: они по определению правильные — редактор
    смотрел глазами. Разметка самих классификаторов в примеры не идёт,
    иначе модель училась бы на собственных ошибках.
    """

    limit = limit if limit is not None else settings.classifier_example_count
    if limit <= 0:
        return []

    query = examples_query(limit, exclude_news_id)

    examples: list[LabeledExample] = []
    for news in (await session.execute(query)).unique().scalars().all():
        labels: dict[str, list[str]] = {}
        for label in news.labels:
            if label.origin != "manual":
                continue
            labels.setdefault(label.facet.slug, []).append(label.value.slug)
        if not labels:
            continue

        body = news.body_md[:EXAMPLE_BODY_CHARS]
        if len(news.body_md) > EXAMPLE_BODY_CHARS:
            body += "…"
        examples.append(LabeledExample(title=news.title, body_md=body, labels=labels))
    return examples
