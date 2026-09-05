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


# --------------------------------------------------------------------------- #
# Ответ модели, которого может не быть
# --------------------------------------------------------------------------- #

_content_of = ai_classifier._content_of


def test_plain_content_is_returned():
    body = {"choices": [{"message": {"content": '{"labels": []}'}}]}
    assert _content_of(body, "m") == '{"labels": []}'


def test_empty_content_falls_back_to_reasoning():
    """Рассуждающая модель тратит бюджет на размышления и оставляет content пустым."""

    body = {"choices": [{"message": {"content": None, "reasoning": 'итак, {"labels": []}'}}]}
    assert "labels" in _content_of(body, "m")


def test_blank_content_also_falls_back():
    body = {"choices": [{"message": {"content": "   ", "reasoning": '{"labels": []}'}}]}
    assert _content_of(body, "m") == '{"labels": []}'


def test_completely_empty_answer_names_the_likely_cause():
    body = {"choices": [{"message": {"content": None}, "finish_reason": "length"}]}
    with pytest.raises(RuntimeError, match="max_tokens"):
        _content_of(body, "deepseek/v4")


def test_provider_error_is_surfaced_not_swallowed():
    body = {"error": {"message": "rate limited"}}
    with pytest.raises(RuntimeError, match="rate limited"):
        _content_of(body, "m")


def test_no_choices_at_all():
    with pytest.raises(RuntimeError, match="ни одного варианта"):
        _content_of({"choices": []}, "m")


# --------------------------------------------------------------------------- #
# База знаний: контекст организации и примеры ручной разметки
# --------------------------------------------------------------------------- #

_context_prompt = ai_classifier._context_prompt
_examples_prompt = ai_classifier._examples_prompt


def request_with(**kwargs) -> ClassifyRequest:
    return ClassifyRequest(
        request_id="r",
        news=ClassifyNews(id="n", body_md="текст"),
        taxonomy=TAXONOMY,
        options=ClassifyOptions(),
        **kwargs,
    )


def test_context_reaches_the_prompt():
    prompt = _context_prompt(request_with(context="ВКР — выпускная работа."))
    assert "ВКР — выпускная работа." in prompt


def test_missing_context_adds_nothing():
    assert _context_prompt(request_with()) == ""
    assert _context_prompt(request_with(context="   ")) == ""


def test_examples_carry_the_editors_labels():
    from thirdnews_contracts import LabeledExample

    prompt = _examples_prompt(
        request_with(
            examples=[
                LabeledExample(
                    title="Семинар ВКР",
                    body_md="Встреча с научным руководителем",
                    labels={"importance": ["high"], "stream": ["2024"]},
                )
            ]
        )
    )
    assert "Семинар ВКР" in prompt
    assert "importance" in prompt and "high" in prompt


def test_no_examples_adds_nothing():
    assert _examples_prompt(request_with()) == ""


def test_example_bodies_are_trimmed():
    """Примеров несколько, и целиком они раздули бы каждый запрос."""

    from thirdnews_contracts import LabeledExample

    prompt = _examples_prompt(
        request_with(examples=[LabeledExample(body_md="я" * 5000, labels={"importance": ["high"]})])
    )
    assert len(prompt) < 1200


def test_example_newlines_do_not_break_the_block():
    from thirdnews_contracts import LabeledExample

    prompt = _examples_prompt(
        request_with(
            examples=[LabeledExample(body_md="строка\n\nдругая", labels={"importance": ["high"]})]
        )
    )
    assert "текст: строка другая" in prompt


def test_contract_keeps_both_fields_optional():
    """Классификатор, который их игнорирует, обязан остаться совместимым."""

    plain = ClassifyRequest.model_validate(
        {"request_id": "r", "news": {"id": "n", "body_md": "t"}, "taxonomy": {"facets": []}}
    )
    assert plain.context is None
    assert plain.examples == []


# --------------------------------------------------------------------------- #
# Разбиение на сборку запроса / вызов / разбор — для измерителя tools/eval
# --------------------------------------------------------------------------- #


def test_build_payload_is_deterministic_and_complete():
    payload = ai_classifier.build_payload(request())
    assert payload["model"] == ai_classifier.DEFAULT_MODEL
    assert payload["temperature"] == 0.0
    assert payload["response_format"] == {"type": "json_object"}
    assert [m["role"] for m in payload["messages"]] == ["system", "user"]
    assert "Новость:" in payload["messages"][1]["content"]
    assert ai_classifier.build_payload(request()) == payload


def test_build_payload_honours_registration_config():
    req = request()
    req.options.config = {
        "model": "openai/gpt-4o-mini",
        "temperature": 0.3,
        "instructions": "Будь краток.",
    }
    payload = ai_classifier.build_payload(req)
    assert payload["model"] == "openai/gpt-4o-mini"
    assert payload["temperature"] == 0.3
    assert "Будь краток." in payload["messages"][1]["content"]


def test_parse_response_filters_by_taxonomy():
    content = (
        '{"labels": [{"facet": "importance", "value": "high", "confidence": 0.9},'
        ' {"facet": "importance", "value": "nope", "confidence": 0.9}]}'
    )
    body = {"choices": [{"message": {"content": content}}]}
    labels = ai_classifier.parse_response(request(), body)
    assert [(label.facet, label.value) for label in labels] == [("importance", "high")]
