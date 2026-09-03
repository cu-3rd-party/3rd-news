"""The LLM classifier must never be trusted to stay inside the taxonomy."""

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

from .conftest import ai_classifier

_extract_json = ai_classifier._extract_json
_taxonomy_prompt = ai_classifier._taxonomy_prompt
_valid_labels = ai_classifier._valid_labels

TAXONOMY = Taxonomy(
    facets=[
        FacetSchema(
            slug="importance",
            title="Важность",
            type="single",
            values=[
                FacetValueSchema(slug="high", title="Важно"),
                FacetValueSchema(slug="low", title="Не важно"),
            ],
        ),
        FacetSchema(
            slug="stream",
            title="Поток",
            type="multi",
            values=[
                FacetValueSchema(slug="2024", title="2024"),
                FacetValueSchema(slug="2025", title="2025"),
            ],
        ),
    ]
)


def request(min_confidence: float = 0.0) -> ClassifyRequest:
    return ClassifyRequest(
        request_id="r",
        news=ClassifyNews(id="n", body_md="текст"),
        taxonomy=TAXONOMY,
        options=ClassifyOptions(min_confidence=min_confidence),
    )


def test_unknown_facet_or_value_is_dropped():
    raw = {
        "labels": [
            {"facet": "importance", "value": "high", "confidence": 0.9},
            {"facet": "importance", "value": "invented", "confidence": 0.9},
            {"facet": "nonexistent", "value": "high", "confidence": 0.9},
        ]
    }
    labels = _valid_labels(request(), raw)
    assert [(label.facet, label.value) for label in labels] == [("importance", "high")]


def test_single_facet_keeps_only_the_first_answer():
    raw = {
        "labels": [
            {"facet": "importance", "value": "high", "confidence": 0.9},
            {"facet": "importance", "value": "low", "confidence": 0.8},
        ]
    }
    labels = _valid_labels(request(), raw)
    assert len(labels) == 1
    assert labels[0].value == "high"


def test_multi_facet_keeps_several_answers():
    raw = {
        "labels": [
            {"facet": "stream", "value": "2024", "confidence": 0.8},
            {"facet": "stream", "value": "2025", "confidence": 0.8},
        ]
    }
    assert len(_valid_labels(request(), raw)) == 2


def test_confidence_is_clamped_and_filtered():
    raw = {
        "labels": [
            {"facet": "importance", "value": "high", "confidence": 42},
            {"facet": "stream", "value": "2024", "confidence": 0.1},
        ]
    }
    labels = _valid_labels(request(min_confidence=0.5), raw)
    assert len(labels) == 1
    assert labels[0].confidence == 1.0


def test_garbage_confidence_falls_back_to_a_default():
    raw = {"labels": [{"facet": "importance", "value": "high", "confidence": "не знаю"}]}
    assert _valid_labels(request(), raw)[0].confidence == pytest.approx(0.7)


def test_extract_json_handles_prose_around_the_object():
    content = 'Конечно! Вот ответ:\n```json\n{"labels": []}\n```\nГотово.'
    assert _extract_json(content) == {"labels": []}


def test_extract_json_raises_when_there_is_no_object():
    with pytest.raises(ValueError):
        _extract_json("извините, не могу")


def test_taxonomy_prompt_lists_every_facet_and_value():
    prompt = _taxonomy_prompt(request())
    for token in ("importance", "stream", "high", "low", "2024", "2025", "type=single"):
        assert token in prompt


def test_taxonomy_prompt_respects_the_requested_facets():
    scoped = ClassifyRequest(
        request_id="r",
        news=ClassifyNews(id="n", body_md="текст"),
        taxonomy=TAXONOMY,
        options=ClassifyOptions(facets=["stream"]),
    )
    prompt = _taxonomy_prompt(scoped)
    assert "stream" in prompt
    assert "importance" not in prompt
