import re
from functools import lru_cache

from thirdnews_contracts import ClassifyRequest, Evidence, ProposedLabel

from ...domain.entities.classifier import IDENTITY
from ...domain.entities.rule import (
    BASE_CONFIDENCE,
    MAX_CONFIDENCE,
    MAX_PATTERN_LENGTH,
    PER_EXTRA_HIT,
)

SLUG = IDENTITY.slug
VERSION = IDENTITY.version


@lru_cache(maxsize=4096)
def compile_rule(pattern: str, is_keyword: bool) -> re.Pattern[str] | None:
    if not pattern or len(pattern) > MAX_PATTERN_LENGTH:
        return None
    try:
        source = rf"(?<!\w){re.escape(pattern)}" if is_keyword else pattern
        return re.compile(source, re.IGNORECASE | re.UNICODE)
    except re.error:
        return None


def news_text(request: ClassifyRequest) -> str:
    news = request.news
    parts = [news.title or "", news.body_md, news.source_text or ""]
    for item in news.attachments:
        parts.extend((item.caption or "", item.extracted_text or ""))
    return "\n".join(parts)


def classify(request: ClassifyRequest) -> list[ProposedLabel]:
    text = news_text(request)
    allowed = set(request.options.allowed_axes)
    labels: list[ProposedLabel] = []
    for axis in request.taxonomy.facets:
        if allowed and axis.slug not in allowed:
            continue
        matches: list[tuple[float, ProposedLabel]] = []
        for value in axis.values:
            hits: list[str] = []
            for keyword in value.synonyms:
                rule = compile_rule(keyword, True)
                if rule is not None and rule.search(text):
                    hits.append(keyword)
            for pattern in value.match_patterns:
                rule = compile_rule(pattern, False)
                if rule is not None and rule.search(text):
                    hits.append(pattern)
            if not hits:
                continue
            confidence = min(MAX_CONFIDENCE, BASE_CONFIDENCE + PER_EXTRA_HIT * (len(hits) - 1))
            matches.append(
                (
                    confidence,
                    ProposedLabel(
                        axis=axis.slug,
                        value=value.slug,
                        confidence=confidence,
                        reason="matched configured rules",
                        evidence=[Evidence(kind="rule", excerpt=hit[:500]) for hit in hits[:5]],
                    ),
                )
            )
        matches.sort(key=lambda item: item[0], reverse=True)
        chosen = matches[:1] if axis.type.value == "single" else matches
        labels.extend(
            label for confidence, label in chosen if confidence >= request.options.min_confidence
        )
    return labels
