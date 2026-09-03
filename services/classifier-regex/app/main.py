"""Keyword / regular-expression classifier.

Stateless by design: every rule it applies comes from the taxonomy in the
request (`synonyms` and `match_patterns` on each facet value), which an editor
maintains in the main service's admin. Adding a keyword is an admin edit, not
a deploy of this service.
"""

from __future__ import annotations

import os
import re
from functools import lru_cache

from thirdnews_contracts import ClassifyRequest, ProposedLabel
from thirdnews_contracts.worker import build_classifier_app

SLUG = "regex"
SECRET = os.getenv("CLASSIFIER_SECRET") or None

#: A value matched by N rules is more likely right than one matched by a single
#: keyword, but we never claim certainty from keywords alone.
BASE_CONFIDENCE = 0.6
PER_EXTRA_HIT = 0.1
MAX_CONFIDENCE = 0.95


@lru_cache(maxsize=4096)
def _compile(pattern: str, is_keyword: bool) -> re.Pattern[str] | None:
    """Compile one rule, tolerating a broken regex written in the admin."""

    try:
        if is_keyword:
            # Word-ish boundaries, so "МГУ" does not match inside another word,
            # while still allowing Russian morphology to follow the stem.
            return re.compile(rf"(?<!\w){re.escape(pattern)}", re.IGNORECASE | re.UNICODE)
        return re.compile(pattern, re.IGNORECASE | re.UNICODE)
    except re.error:
        return None


def _haystack(request: ClassifyRequest) -> str:
    news = request.news
    parts = [news.title or "", news.body_md, news.source_text or ""]
    parts.extend(item.caption or "" for item in news.attachments)
    return "\n".join(parts)


def classify(request: ClassifyRequest) -> list[ProposedLabel]:
    text = _haystack(request)
    wanted = set(request.options.facets or [])
    labels: list[ProposedLabel] = []

    for facet in request.taxonomy.facets:
        if wanted and facet.slug not in wanted:
            continue

        scored: list[tuple[float, ProposedLabel]] = []
        for value in facet.values:
            hits: list[str] = []
            for keyword in value.synonyms:
                rule = _compile(keyword, True)
                if rule and rule.search(text):
                    hits.append(keyword)
            for pattern in value.match_patterns:
                rule = _compile(pattern, False)
                if rule and rule.search(text):
                    hits.append(pattern)
            if not hits:
                continue

            confidence = min(
                MAX_CONFIDENCE, BASE_CONFIDENCE + PER_EXTRA_HIT * (len(hits) - 1)
            )
            scored.append(
                (
                    confidence,
                    ProposedLabel(
                        facet=facet.slug,
                        value=value.slug,
                        confidence=confidence,
                        reason="matched: " + ", ".join(hits[:5]),
                    ),
                )
            )

        if not scored:
            continue
        scored.sort(key=lambda item: item[0], reverse=True)
        # A single-valued facet gets the best match only; a multi-valued one
        # gets everything that matched.
        chosen = scored[:1] if facet.type == "single" else scored
        labels.extend(label for _confidence, label in chosen)

    return [
        label for label in labels if label.confidence >= request.options.min_confidence
    ]


app = build_classifier_app(
    slug=SLUG,
    name="Regex / keyword classifier",
    classify=classify,
    secret=SECRET,
    version="0.1.0",
    description="Applies the synonyms and match_patterns configured on each facet value.",
)
