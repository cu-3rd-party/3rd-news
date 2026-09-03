"""First-boot setup: an admin account and a small starter taxonomy.

Runs on every start and does nothing when the tables already have rows, so it
is safe to leave enabled in production.
"""

from __future__ import annotations

import logging

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings
from .models import Facet, FacetValue, User
from .security import hash_password

logger = logging.getLogger("3rdnews.bootstrap")

#: Deliberately close to the examples in the brief; delete or edit in the admin.
STARTER_TAXONOMY = [
    {
        "slug": "importance",
        "title": "Важность",
        "type": "single",
        "ai_hint": "Насколько новость важна для среднего студента.",
        "values": [
            ("critical", "Очень важно", ["срочно", "дедлайн", "обязательно", "отчисление"]),
            ("normal", "Не очень важно", []),
            ("low", "Совсем не важно", []),
        ],
    },
    {
        "slug": "stream",
        "title": "Поток",
        "type": "multi",
        "ai_hint": "Год поступления, к которому относится новость.",
        "values": [
            ("2024", "2024", ["1 курс", "первокурсник"]),
            ("2025", "2025", ["2 курс"]),
            ("2026", "2026", ["3 курс"]),
        ],
    },
    {
        "slug": "kind",
        "title": "Тип",
        "type": "single",
        "values": [
            ("event", "Мероприятие", ["мероприятие", "фестиваль", "концерт"]),
            ("announcement", "Анонс", ["анонс", "приглашаем", "регистрация"]),
            ("news", "Событие", []),
        ],
    },
    {
        "slug": "audience",
        "title": "Формат",
        "type": "single",
        "values": [
            ("external", "Внешние спикеры", ["спикер", "гость", "лекция от"]),
            ("internal", "Внутреннее мероприятие", []),
        ],
    },
]


async def bootstrap(session: AsyncSession) -> None:
    await _ensure_admin(session)
    await _ensure_taxonomy(session)
    await session.commit()


async def _ensure_admin(session: AsyncSession) -> None:
    if not settings.bootstrap_admin_email or not settings.bootstrap_admin_password:
        return
    existing = (await session.execute(select(func.count()).select_from(User))).scalar_one()
    if existing:
        return
    session.add(
        User(
            email=settings.bootstrap_admin_email.lower(),
            full_name="Bootstrap admin",
            password_hash=hash_password(settings.bootstrap_admin_password),
            role="admin",
        )
    )
    logger.info("created bootstrap admin %s", settings.bootstrap_admin_email)


async def _ensure_taxonomy(session: AsyncSession) -> None:
    existing = (await session.execute(select(func.count()).select_from(Facet))).scalar_one()
    if existing:
        return
    for position, spec in enumerate(STARTER_TAXONOMY):
        facet = Facet(
            slug=spec["slug"],
            title=spec["title"],
            type=spec["type"],
            ai_hint=spec.get("ai_hint"),
            position=position,
        )
        session.add(facet)
        await session.flush()
        for value_position, (slug, title, synonyms) in enumerate(spec["values"]):
            session.add(
                FacetValue(
                    facet_id=facet.id,
                    slug=slug,
                    title=title,
                    synonyms=list(synonyms),
                    position=value_position,
                )
            )
    logger.info("seeded starter taxonomy with %d facets", len(STARTER_TAXONOMY))
