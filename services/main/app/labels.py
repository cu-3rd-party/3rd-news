"""Turning many opinions about a news item into one answer.

A news item can be labelled by an editor, by the source's defaults, by the
parser and by any number of classifiers, and they will disagree. All of it is
kept in `news_labels`; this module decides what `news_effective_labels` — the
table the delivery endpoint filters on — should contain.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings
from .models import (
    Classifier,
    Facet,
    FacetValue,
    News,
    NewsEffectiveLabel,
    NewsLabel,
)

@dataclass(slots=True)
class LabelEntry:
    """One (facet, value) claim, with the confidence behind it."""

    facet_id: uuid.UUID
    value_id: uuid.UUID
    confidence: float = 1.0
    reason: str | None = None


#: Who wins when two origins claim the same facet. Higher is stronger.
ORIGIN_RANK = {
    "manual": 400,
    "source_default": 300,
    "parser": 200,
    "classifier": 100,
}


async def resolve_taxonomy_ids(
    session: AsyncSession, labels: dict[str, list[str]]
) -> dict[tuple[str, str], tuple[uuid.UUID, uuid.UUID]]:
    """Map `{"facet-slug": ["value-slug"]}` onto ids, keyed by the slug pair.

    Slugs that do not exist are simply absent from the result rather than
    raising: a classifier inventing a value must not fail the whole item.
    """

    if not labels:
        return {}
    rows = (
        await session.execute(
            select(Facet.slug, Facet.id, FacetValue.slug, FacetValue.id)
            .join(FacetValue, FacetValue.facet_id == Facet.id)
            .where(Facet.slug.in_(labels.keys()))
        )
    ).all()
    index = {(f_slug, v_slug): (f_id, v_id) for f_slug, f_id, v_slug, v_id in rows}

    return {
        (facet_slug, value_slug): index[(facet_slug, value_slug)]
        for facet_slug, value_slugs in labels.items()
        for value_slug in value_slugs
        if (facet_slug, value_slug) in index
    }


def entries_from(
    resolved: dict[tuple[str, str], tuple[uuid.UUID, uuid.UUID]],
    confidences: dict[tuple[str, str], float] | None = None,
    reasons: dict[tuple[str, str], str] | None = None,
) -> list[LabelEntry]:
    """Turn a resolution map into rows ready for `record_labels`."""

    return [
        LabelEntry(
            facet_id=facet_id,
            value_id=value_id,
            confidence=(confidences or {}).get(key, 1.0),
            reason=(reasons or {}).get(key),
        )
        for key, (facet_id, value_id) in resolved.items()
    ]


async def record_labels(
    session: AsyncSession,
    news_id: uuid.UUID,
    entries: list[LabelEntry],
    *,
    origin: str,
    origin_key: str = "",
    user_id: uuid.UUID | None = None,
    replace_origin: bool = True,
) -> None:
    """Store one origin's opinion, replacing whatever it said before."""

    if replace_origin:
        await session.execute(
            delete(NewsLabel).where(
                NewsLabel.news_id == news_id,
                NewsLabel.origin == origin,
                NewsLabel.origin_key == origin_key,
            )
        )
    for entry in entries:
        session.add(
            NewsLabel(
                news_id=news_id,
                facet_id=entry.facet_id,
                value_id=entry.value_id,
                origin=origin,
                origin_key=origin_key,
                confidence=entry.confidence,
                reason=entry.reason,
                created_by_user_id=user_id,
            )
        )
    await session.flush()


async def recompute_effective(session: AsyncSession, news_id: uuid.UUID) -> None:
    """Rebuild `news_effective_labels` for one item."""

    news = (await session.execute(select(News).where(News.id == news_id))).scalar_one_or_none()
    if news is None:
        return

    facets = (
        (await session.execute(select(Facet).where(Facet.is_active.is_(True)))).scalars().all()
    )

    opinions = (
        (await session.execute(select(NewsLabel).where(NewsLabel.news_id == news_id)))
        .scalars()
        .all()
    )
    classifiers = (await session.execute(select(Classifier))).scalars().all()
    classifier_by_slug = {c.slug: c for c in classifiers}

    manual_facets = set(news.manual_facets or [])

    def usable(label: NewsLabel) -> bool:
        if label.origin != "classifier":
            return True
        classifier = classifier_by_slug.get(label.origin_key)
        if classifier is None:
            # The registration is gone; keep the history, drop the authority.
            return False
        if not classifier.is_active or not classifier.auto_apply:
            return False
        threshold = max(classifier.min_confidence, settings.default_min_confidence)
        return label.confidence >= threshold

    def tier(label: NewsLabel) -> tuple[int, int]:
        rank = ORIGIN_RANK.get(label.origin, 0)
        classifier = classifier_by_slug.get(label.origin_key)
        return rank, classifier.priority if classifier else 0

    selected: list[tuple[NewsLabel, Facet]] = []
    for facet in facets:
        candidates = [
            label
            for label in opinions
            if label.facet_id == facet.id and (label.origin == "manual" or usable(label))
        ]
        if facet.slug in manual_facets:
            # The editor's word is final, empty included.
            candidates = [label for label in candidates if label.origin == "manual"]
        if not candidates:
            continue

        candidates.sort(key=lambda label: (*tier(label), label.confidence), reverse=True)
        best_tier = tier(candidates[0])
        winners = [label for label in candidates if tier(label) == best_tier]
        if facet.type == "single":
            winners = winners[:1]
        selected.extend((label, facet) for label in winners)

    await session.execute(
        delete(NewsEffectiveLabel).where(NewsEffectiveLabel.news_id == news_id)
    )
    seen: set[uuid.UUID] = set()
    for label, _facet in selected:
        if label.value_id in seen:
            continue
        seen.add(label.value_id)
        session.add(
            NewsEffectiveLabel(
                news_id=news_id,
                value_id=label.value_id,
                facet_id=label.facet_id,
                origin=label.origin,
                confidence=label.confidence,
            )
        )

    _update_status(news, facets, {facet.id for _label, facet in selected})
    await session.flush()


def _update_status(news: News, facets: list[Facet], labelled_facet_ids: set[uuid.UUID]) -> None:
    """Move the item along pending -> published / needs_review."""

    if news.status in {"rejected", "archived"}:
        return
    missing_required = [
        facet for facet in facets if facet.required and facet.id not in labelled_facet_ids
    ]
    if news.classified_at is None:
        return
    if missing_required:
        news.status = "needs_review"
    elif settings.auto_publish and news.status in {"pending", "needs_review"}:
        news.status = "published"


async def mark_classification_finished(session: AsyncSession, news_id: uuid.UUID) -> None:
    news = (await session.execute(select(News).where(News.id == news_id))).scalar_one_or_none()
    if news is None:
        return
    news.classified_at = datetime.now(timezone.utc)
    await session.flush()
    await recompute_effective(session, news_id)


async def set_manual_labels(
    session: AsyncSession,
    news: News,
    labels: dict[str, list[str]],
    release_facets: list[str],
    user_id: uuid.UUID | None = None,
) -> None:
    """Apply an editor's decision, facet by facet.

    Listing a facet with an empty value list is meaningful: it records "an
    editor looked and decided this facet does not apply", which classifiers
    must not undo. `release_facets` is the opposite — hand the facet back.
    """

    touched = set(labels) | set(release_facets)
    if not touched:
        return

    facets = (
        (await session.execute(select(Facet).where(Facet.slug.in_(touched)))).scalars().all()
    )
    facet_by_slug = {facet.slug: facet for facet in facets}
    unknown = touched - set(facet_by_slug)
    if unknown:
        raise ValueError(f"unknown facets: {', '.join(sorted(unknown))}")

    await session.execute(
        delete(NewsLabel).where(
            NewsLabel.news_id == news.id,
            NewsLabel.origin == "manual",
            NewsLabel.facet_id.in_([facet_by_slug[slug].id for slug in touched]),
        )
    )

    values = (
        (
            await session.execute(
                select(FacetValue).where(
                    FacetValue.facet_id.in_([facet_by_slug[slug].id for slug in labels])
                )
            )
        )
        .scalars()
        .all()
    ) if labels else []
    value_by_key = {(value.facet_id, value.slug): value for value in values}

    for facet_slug, value_slugs in labels.items():
        facet = facet_by_slug[facet_slug]
        for value_slug in value_slugs:
            value = value_by_key.get((facet.id, value_slug))
            if value is None:
                raise ValueError(f"unknown value {facet_slug}/{value_slug}")
            session.add(
                NewsLabel(
                    news_id=news.id,
                    facet_id=facet.id,
                    value_id=value.id,
                    origin="manual",
                    origin_key=str(user_id) if user_id else "",
                    confidence=1.0,
                    created_by_user_id=user_id,
                )
            )

    manual = set(news.manual_facets or [])
    manual |= set(labels)
    manual -= set(release_facets)
    news.manual_facets = sorted(manual)

    await session.flush()
    await recompute_effective(session, news.id)
