from __future__ import annotations

from typing import Any

from lib.infra.storage.postgres.models import (
    Classifier,
    EditorialRule,
    Facet,
    FacetValue,
    ManualLabelDecision,
    News,
    NewsEffectiveLabel,
    NewsLabel,
)
from lib.interactor.use_cases.scoring import evaluate_scores
from sqlalchemy import delete, select

from .classifier_attempts import ClassifierAttempts
from .manual_decisions import ManualLabelDecisions


class LabelMaterializer:
    ORIGIN_PRIORITY = {
        "classifier": 100,
        "parser": 200,
        "source_default": 300,
        "manual": 1000,
    }

    async def recompute(self, session: Any, news: News) -> None:
        await session.execute(
            delete(NewsEffectiveLabel).where(NewsEffectiveLabel.news_id == news.id)
        )
        rows = (
            await session.execute(
                select(NewsLabel, Facet, FacetValue)
                .join(Facet, Facet.id == NewsLabel.facet_id)
                .join(FacetValue, FacetValue.id == NewsLabel.value_id)
                .where(
                    NewsLabel.news_id == news.id,
                    NewsLabel.version_id == news.current_version_id,
                    Facet.enabled.is_(True),
                    FacetValue.enabled.is_(True),
                )
            )
        ).all()
        classifiers = (await session.scalars(select(Classifier))).all()
        classifier_by_slug = {item.slug: item for item in classifiers}
        latest_attempt = await ClassifierAttempts().latest(
            session, news.id, news.current_version_id, classifiers
        )
        manual_decisions = await ManualLabelDecisions().latest(
            session, news.id, news.current_version_id
        )
        decision_axes = set(
            await session.scalars(
                select(Facet.slug)
                .join(ManualLabelDecision, ManualLabelDecision.facet_id == Facet.id)
                .where(
                    ManualLabelDecision.news_id == news.id,
                    ManualLabelDecision.version_id == news.current_version_id,
                    ManualLabelDecision.origin == "manual",
                )
            )
        )
        grouped: dict[str, list[tuple[NewsLabel, Facet, FacetValue]]] = {}
        for label, facet, value in rows:
            if label.origin == "provenance":
                continue
            if label.origin in {"classifier", "shadow"}:
                slug, separator, attempt_id = label.origin_key.partition(":")
                if not separator or latest_attempt.get(slug) != attempt_id:
                    continue
                classifier = classifier_by_slug.get(slug)
                if (
                    classifier is None
                    or not classifier.enabled
                    or classifier.shadow
                    or (classifier.allowed_axes and facet.slug not in classifier.allowed_axes)
                    or label.confidence < classifier.min_confidence
                ):
                    continue
            grouped.setdefault(facet.slug, []).append((label, facet, value))

        legacy_manual = set(news.manual_facets) - decision_axes
        active_manual = legacy_manual | {
            slug for slug, decision in manual_decisions.items() if decision.action == "set"
        }
        news.manual_facets = sorted(active_manual)
        selected_labels: dict[str, list[str]] = {}
        axes = set(grouped) | active_manual
        for axis in axes:
            candidates = grouped.get(axis, [])
            decision = manual_decisions.get(axis)
            if decision is not None and decision.action == "set":
                candidates = [
                    entry
                    for entry in candidates
                    if entry[0].origin == "manual" and entry[0].origin_key == str(decision.id)
                ]
            elif decision is not None and decision.action == "release":
                candidates = [entry for entry in candidates if entry[0].origin != "manual"]
            elif axis in legacy_manual:
                candidates = [entry for entry in candidates if entry[0].origin == "manual"]
            if not candidates:
                continue
            opinion_groups: dict[tuple[str, str], list[tuple[NewsLabel, Facet, FacetValue]]] = {}
            for entry in candidates:
                label = entry[0]
                opinion_groups.setdefault((label.origin, label.origin_key), []).append(entry)
            winning_key = max(
                opinion_groups,
                key=lambda key: self.opinion_priority(key, classifier_by_slug),
            )
            winners = opinion_groups[winning_key]
            facet = winners[0][1]
            winners.sort(key=lambda entry: (-entry[0].confidence, entry[2].slug))
            if facet.kind != "multi":
                winners = winners[:1]
            selected_labels[axis] = [entry[2].slug for entry in winners]
            for label, _, value in winners:
                session.add(
                    NewsEffectiveLabel(
                        news_id=news.id,
                        facet_id=label.facet_id,
                        value_id=value.id,
                        origin=label.origin,
                        confidence=label.confidence,
                    )
                )

        rules = (
            await session.scalars(
                select(EditorialRule)
                .where(EditorialRule.enabled.is_(True))
                .order_by(EditorialRule.version)
            )
        ).all()
        scores = evaluate_scores(
            selected_labels,
            [{**item.definition, "id": str(item.id), "enabled": True} for item in rules],
        )
        news.urgency = scores.urgency
        news.impact = scores.impact
        news.editorial_priority = scores.editorial_priority
        news.importance = scores.importance
        news.revision += 1
        news.visibility_revision += 1

    def opinion_priority(
        self, key: tuple[str, str], classifier_by_slug: dict[str, Classifier]
    ) -> tuple[int, int, str]:
        origin, origin_key = key
        slug = origin_key.partition(":")[0]
        classifier = classifier_by_slug.get(slug)
        return (
            self.ORIGIN_PRIORITY.get("classifier" if origin == "shadow" else origin, 0),
            classifier.priority if classifier is not None else 0,
            origin_key,
        )
