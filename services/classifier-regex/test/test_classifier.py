from __future__ import annotations

import pytest
from thirdnews_contracts import (
    ClassifyNews,
    ClassifyOptions,
    ClassifyRequest,
    FacetSchema,
    FacetType,
    FacetValueSchema,
    Taxonomy,
)

from lib.interactor.use_cases.classify import classify

IMPORTANCE = FacetSchema(
    slug="importance",
    title="Важность",
    type=FacetType.SINGLE,
    values=[
        FacetValueSchema(slug="critical", title="Очень важно", synonyms=["дедлайн", "срочно"]),
        FacetValueSchema(slug="low", title="Не важно", synonyms=["кружок"]),
    ],
)
STREAM = FacetSchema(
    slug="stream",
    title="Поток",
    type=FacetType.MULTI,
    values=[
        FacetValueSchema(slug="2024", title="2024", match_patterns=[r"\b2024\b"]),
        FacetValueSchema(slug="2025", title="2025", match_patterns=[r"\b2025\b"]),
    ],
)


def request(
    body: str,
    *,
    facets: list[FacetSchema] | None = None,
    allowed_axes: list[str] | None = None,
    min_confidence: float = 0,
) -> ClassifyRequest:
    return ClassifyRequest(
        request_id="r",
        job_id="j",
        attempt_id="a",
        news=ClassifyNews(id="n", version=1, body_md=body),
        taxonomy=Taxonomy(version="7", facets=facets or [IMPORTANCE, STREAM]),
        options=ClassifyOptions(allowed_axes=allowed_axes or [], min_confidence=min_confidence),
    )


def test_single_axis_selects_only_the_strongest_value() -> None:
    labels = classify(request("Срочно: дедлайн. Ещё есть кружок.", facets=[IMPORTANCE]))
    assert [(label.axis, label.value) for label in labels] == [("importance", "critical")]
    assert labels[0].confidence == pytest.approx(0.7)
    assert [item.excerpt for item in labels[0].evidence] == ["дедлайн", "срочно"]


def test_multi_axis_keeps_every_matching_value() -> None:
    labels = classify(request("Для потоков 2024 и 2025", facets=[STREAM]))
    assert sorted(label.value for label in labels) == ["2024", "2025"]


def test_more_hits_raise_confidence_and_threshold_filters() -> None:
    one = classify(request("дедлайн", facets=[IMPORTANCE]))[0]
    two = classify(request("срочно, дедлайн", facets=[IMPORTANCE]))[0]
    assert two.confidence > one.confidence
    assert classify(request("дедлайн", facets=[IMPORTANCE], min_confidence=0.99)) == []


def test_broken_or_excessive_regex_is_ignored() -> None:
    broken = FacetSchema(
        slug="broken",
        title="Broken",
        values=[
            FacetValueSchema(
                slug="v",
                title="V",
                match_patterns=["([unclosed", "x" * 501],
            )
        ],
    )
    assert classify(request("anything", facets=[broken])) == []


def test_classifier_never_crosses_allowed_axis_boundary() -> None:
    labels = classify(request("дедлайн в 2024", allowed_axes=["stream"]))
    assert {(item.axis, item.value) for item in labels} == {("stream", "2024")}


@pytest.mark.parametrize("body", ["ДЕДЛАЙН", "Дедлайн", "дедлайн"])
def test_matching_is_case_insensitive(body: str) -> None:
    assert classify(request(body, facets=[IMPORTANCE]))


def test_attachment_text_and_caption_participate_in_matching() -> None:
    from thirdnews_contracts import ClassifyAttachment

    item = request("обычный текст", facets=[IMPORTANCE])
    item.news.attachments = [
        ClassifyAttachment(kind="document", caption="Срочно", extracted_text="дедлайн")
    ]
    assert classify(item)[0].value == "critical"
