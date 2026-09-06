from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import aiohttp
import pytest
from thirdnews_contracts import (
    ClassificationStatus,
    ClassifyNews,
    ClassifyOptions,
    ClassifyRequest,
    FacetSchema,
    FacetType,
    FacetValueSchema,
    LabeledExample,
    Taxonomy,
)

from lib.core.config import Settings, get_settings
from lib.domain.entities.response_schema import RESPONSE_SCHEMA
from lib.infra.clients.response_reader import bounded_json
from lib.interactor.interfaces.clients.provider import ProviderClient
from lib.interactor.use_cases.ai_classification import AIClassification
from lib.interactor.use_cases.build_payload import build_payload
from lib.interactor.use_cases.normalize_response import content, labels
from lib.interactor.use_cases.trace_parameters import trace_parameters

settings = get_settings()

TAXONOMY = Taxonomy(
    version="tax-9",
    facets=[
        FacetSchema(
            slug="importance",
            title="Важность",
            type=FacetType.SINGLE,
            values=[
                FacetValueSchema(slug="high", title="Важно"),
                FacetValueSchema(slug="low", title="Не важно"),
            ],
        ),
        FacetSchema(
            slug="stream",
            title="Поток",
            type=FacetType.MULTI,
            values=[
                FacetValueSchema(slug="2024", title="2024"),
                FacetValueSchema(slug="2025", title="2025"),
            ],
        ),
    ],
)


def test_openai_provider_requires_a_real_api_key() -> None:
    with pytest.raises(ValueError):
        Settings.model_validate(
            {"provider_protocol": "openai", "openai_api_key": "ollama"}
        ).require_openai_key()
    assert (
        Settings.model_validate(
            {"provider_protocol": "openai", "openai_api_key": "secret"}
        ).require_openai_key()
        == "secret"
    )
    assert (
        Settings.model_validate({"provider_protocol": "ollama-native"}).require_openai_key() == ""
    )


def request(*, min_confidence: float = 0, allowed_axes: list[str] | None = None) -> ClassifyRequest:
    return ClassifyRequest(
        request_id="r",
        job_id="j",
        attempt_id="a",
        news=ClassifyNews(id="n", version=4, title="Заголовок", body_md="текст"),
        taxonomy=TAXONOMY,
        options=ClassifyOptions(allowed_axes=allowed_axes or [], min_confidence=min_confidence),
    )


def test_payload_is_deterministic_structured_and_includes_context_and_examples() -> None:
    item = request(allowed_axes=["stream"])
    item.context = "ВКР — выпускная работа."
    item.examples = [
        LabeledExample(
            body_md="Встреча с научным руководителем",
            labels={"stream": ["2024"]},
        )
    ]
    payload = build_payload(item, settings)
    assert payload == build_payload(item, settings)
    assert payload["temperature"] == 0
    assert payload["response_format"]["type"] == "json_schema"
    prompt = payload["messages"][1]["content"]
    assert "ВКР — выпускная работа." in prompt
    assert "Встреча с научным руководителем" in prompt
    assert '"axis": "stream"' in prompt
    assert '"axis": "importance"' not in prompt


def test_registration_config_controls_model_sampling_and_system_prompt() -> None:
    item = request()
    item.options.config = {
        "model": "local/test-model",
        "temperature": 0.3,
        "max_tokens": 77,
        "reasoning_effort": "none",
        "system_prompt": "Будь краток.",
    }
    payload = build_payload(item, settings)
    assert (payload["model"], payload["temperature"], payload["max_tokens"]) == (
        "local/test-model",
        0.3,
        77,
    )
    assert payload["messages"][0]["content"] == "Будь краток."
    assert payload["reasoning_effort"] == "none"
    assert payload["messages"][1]["content"].startswith("/no_think\n")


def test_registration_can_select_bounded_json_object_compatibility_mode() -> None:
    item = request()
    item.options.config = {"response_format": "json_object"}
    payload = build_payload(item, settings)
    assert payload["response_format"] == {"type": "json_object"}
    assert "Each element" not in payload["messages"][0]["content"]
    assert "labels" in payload["messages"][0]["content"]


def test_unknown_response_format_is_rejected_before_provider_call() -> None:
    item = request()
    item.options.config = {"response_format": "xml"}
    with pytest.raises(ValueError, match="response_format"):
        build_payload(item, settings)


def test_response_normalization_drops_unknown_and_second_single_value() -> None:
    normalized = labels(
        request(),
        {
            "labels": [
                {"axis": "importance", "value": "high", "confidence": 42},
                {"axis": "importance", "value": "low", "confidence": 0.9},
                {"axis": "importance", "value": "invented", "confidence": 0.9},
                {"axis": "made-up", "value": "high", "confidence": 0.9},
                {"axis": "stream", "value": "2024", "confidence": 0.8},
                {"axis": "stream", "value": "2025", "confidence": 0.7},
            ]
        },
    )
    assert [(label.axis, label.value) for label in normalized] == [
        ("importance", "high"),
        ("stream", "2024"),
        ("stream", "2025"),
    ]
    assert normalized[0].confidence == 1


def test_response_normalization_enforces_allowed_axes_threshold_and_evidence() -> None:
    normalized = labels(
        request(min_confidence=0.5, allowed_axes=["stream"]),
        {
            "labels": [
                {"axis": "importance", "value": "high", "confidence": 1},
                {"axis": "stream", "value": "2024", "confidence": 0.1},
                {
                    "axis": "stream",
                    "value": "2025",
                    "confidence": 0.8,
                    "reason": "для потока",
                    "evidence": "2025",
                },
            ]
        },
    )
    assert [(label.axis, label.value) for label in normalized] == [("stream", "2025")]
    assert normalized[0].evidence[0].excerpt == "2025"


@pytest.mark.parametrize(
    "body,error",
    [
        ({"choices": []}, "no choices"),
        ({"choices": [{"message": {"content": None}}]}, "no content"),
        ({"choices": [{"message": {"content": "[]"}}]}, "not an object"),
    ],
)
def test_malformed_provider_responses_are_rejected(body: dict[str, Any], error: str) -> None:
    with pytest.raises((ValueError, TypeError), match=error):
        content(body)


def test_content_parts_are_joined_before_json_validation() -> None:
    assert content(
        {"choices": [{"message": {"content": [{"text": '{"labels":'}, {"text": " []}"}]}}]}
    ) == {"labels": []}


def test_native_ollama_message_is_parsed_with_the_same_validation() -> None:
    assert content({"message": {"content": '{"labels": []}'}}) == {"labels": []}


@pytest.mark.asyncio
async def test_provider_envelope_is_read_with_a_hard_byte_limit(monkeypatch) -> None:
    class Content:
        async def iter_chunked(self, _size: int):
            yield b'{"oversized":"'
            yield b"x" * 32
            yield b'"}'

    response = cast("aiohttp.ClientResponse", SimpleNamespace(content=Content()))
    with pytest.raises(ValueError, match="byte limit"):
        await bounded_json(response, 20)


def test_native_ollama_payload_disables_thinking_and_keeps_json_schema(monkeypatch) -> None:
    monkeypatch.setattr(settings, "provider_protocol", "ollama-native")
    item = request()
    item.options.config = {"reasoning_effort": "none"}
    payload = build_payload(item, settings)
    assert payload["stream"] is False
    assert payload["think"] is False
    assert payload["format"] == RESPONSE_SCHEMA["schema"]
    assert payload["options"]["num_predict"] == settings.max_output_tokens
    parameters = trace_parameters(settings, payload)
    assert parameters["think"] is False
    assert parameters["num_thread"] == settings.ollama_num_threads


@pytest.mark.asyncio
async def test_provider_failure_becomes_auditable_error_result(monkeypatch) -> None:
    class FailedProvider(ProviderClient):
        async def complete(self, payload: dict[str, Any]) -> dict[str, Any]:
            _ = payload
            raise RuntimeError("rate limited")

    response = await AIClassification(settings, FailedProvider()).execute(
        request(allowed_axes=["importance"])
    )
    assert response.status is ClassificationStatus.FAILED
    assert response.error is not None
    assert response.error.code == "provider_error"
    assert response.error.message == "classifier provider request failed"
    assert response.error.retryable is True
    assert response.labels == []
    assert response.skipped == ["importance"]
    assert response.trace is not None
    assert response.trace.error == "RuntimeError: rate limited"
    assert response.trace.request_payload["response_format"]["type"] == "json_schema"


@pytest.mark.asyncio
async def test_valid_provider_result_keeps_raw_response_in_trace(monkeypatch) -> None:
    raw = {
        "choices": [
            {
                "message": {
                    "content": '{"labels":[{"axis":"importance","value":"high","confidence":0.9,"reason":"x","evidence":"текст"}]}'
                }
            }
        ]
    }

    class CompletedProvider(ProviderClient):
        async def complete(self, payload: dict[str, Any]) -> dict[str, Any]:
            _ = payload
            return raw

    response = await AIClassification(settings, CompletedProvider()).execute(request())
    assert response.status is ClassificationStatus.COMPLETED
    assert response.error is None
    assert [(label.axis, label.value) for label in response.labels] == [("importance", "high")]
    assert response.trace is not None
    assert response.trace.raw_response == raw
    assert response.trace.taxonomy_version == "tax-9"
