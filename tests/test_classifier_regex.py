"""The regex classifier reads its rules entirely from the taxonomy it is sent."""

from __future__ import annotations

import pytest
from thirdnews_contracts import (
    ClassifyNews,
    ClassifyOptions,
    ClassifyRequest,
    FacetSchema,
    FacetValueSchema,
    Taxonomy,
)

from .conftest import regex_classifier

classify = regex_classifier.classify


def build_request(body: str, *, facets: list[FacetSchema], min_confidence: float = 0.0):
    return ClassifyRequest(
        request_id="req-1",
        news=ClassifyNews(id="n1", title=None, body_md=body),
        taxonomy=Taxonomy(facets=facets),
        options=ClassifyOptions(min_confidence=min_confidence),
    )


IMPORTANCE = FacetSchema(
    slug="importance",
    title="Важность",
    type="single",
    values=[
        FacetValueSchema(slug="critical", title="Очень важно", synonyms=["дедлайн", "срочно"]),
        FacetValueSchema(slug="low", title="Не важно", synonyms=["кружок"]),
    ],
)
STREAM = FacetSchema(
    slug="stream",
    title="Поток",
    type="multi",
    values=[
        FacetValueSchema(slug="2024", title="2024", match_patterns=[r"\b2024\b"]),
        FacetValueSchema(slug="2025", title="2025", match_patterns=[r"\b2025\b"]),
    ],
)


def test_keyword_match_produces_a_label():
    labels = classify(build_request("Внимание, дедлайн по курсовой!", facets=[IMPORTANCE]))
    assert [(label.facet, label.value) for label in labels] == [("importance", "critical")]
    assert labels[0].reason and "дедлайн" in labels[0].reason


def test_single_facet_yields_at_most_one_value():
    labels = classify(
        build_request("Срочно: дедлайн. Ещё есть кружок.", facets=[IMPORTANCE])
    )
    assert len(labels) == 1
    # Two hits beat one, so the stronger match wins.
    assert labels[0].value == "critical"


def test_multi_facet_yields_every_match():
    labels = classify(build_request("Для потоков 2024 и 2025", facets=[STREAM]))
    assert sorted(label.value for label in labels) == ["2024", "2025"]


def test_more_hits_raise_confidence():
    one = classify(build_request("дедлайн", facets=[IMPORTANCE]))[0]
    two = classify(build_request("срочно, дедлайн", facets=[IMPORTANCE]))[0]
    assert two.confidence > one.confidence


def test_no_match_yields_nothing():
    assert classify(build_request("Обычный текст", facets=[IMPORTANCE, STREAM])) == []


def test_min_confidence_filters_results():
    labels = classify(build_request("дедлайн", facets=[IMPORTANCE], min_confidence=0.99))
    assert labels == []


def test_broken_regex_is_ignored_not_raised():
    facet = FacetSchema(
        slug="broken",
        title="Broken",
        values=[FacetValueSchema(slug="v", title="V", match_patterns=["([unclosed"])],
    )
    assert classify(build_request("anything", facets=[facet])) == []


def test_options_facets_restrict_the_answer():
    request = ClassifyRequest(
        request_id="req-2",
        news=ClassifyNews(id="n1", body_md="дедлайн в 2024"),
        taxonomy=Taxonomy(facets=[IMPORTANCE, STREAM]),
        options=ClassifyOptions(facets=["stream"]),
    )
    labels = classify(request)
    assert {label.facet for label in labels} == {"stream"}


@pytest.mark.parametrize("body", ["ДЕДЛАЙН", "Дедлайн", "дедлайн"])
def test_matching_is_case_insensitive(body):
    assert classify(build_request(body, facets=[IMPORTANCE]))
