from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path

import pytest
from tools.lib.domain.entities.prediction import Prediction
from tools.lib.infra.clients.classifier_runtime import load_classifiers
from tools.lib.interactor.use_cases.eval_dataset import load_records, load_taxonomy
from tools.lib.interactor.use_cases.eval_runners import (
    build_request,
    combine,
    run_ai,
    run_regex,
)

FIX = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def modules():
    return load_classifiers()


def _request(examples=()):
    records = load_records(FIX / "eval_gold.jsonl")
    taxonomy = load_taxonomy(FIX / "eval_taxonomy.json")
    return build_request(
        records[0], taxonomy, list(examples), context=None, config={}, min_confidence=0.0
    )


def _prediction(labels):
    return Prediction(labels=labels, latency_s=0, prompt_tokens=0, completion_tokens=0, cached=True)


def test_request_carries_examples_and_context():
    records = load_records(FIX / "eval_gold.jsonl")
    taxonomy = load_taxonomy(FIX / "eval_taxonomy.json")
    request = build_request(
        records[0],
        taxonomy,
        [records[1]],
        context="ЦУ — университет.",
        config={"model": "m"},
        min_confidence=0.6,
    )
    assert request.news.id == "n1"
    assert request.context == "ЦУ — университет."
    assert request.examples[0].labels == {"importance": ["normal"]}
    assert request.options.config == {"model": "m"}
    assert request.options.min_confidence == 0.6


def test_regex_runner_finds_keywords(modules):
    regex_module, _ = modules
    prediction = run_regex(_request(), regex_module)

    assert prediction.labels["importance"] == [("critical", pytest.approx(0.7))]

    assert prediction.labels.get("stream", []) == []


def test_ai_runner_uses_cache_instead_of_network(modules, tmp_path):
    _, ai_module = modules
    request = _request()
    payload = ai_module.build_payload(request)
    key = hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    content = json.dumps(
        {"labels": [{"axis": "importance", "value": "critical", "confidence": 0.9}]}
    )
    body = {
        "choices": [{"message": {"content": content}}],
        "usage": {"prompt_tokens": 120, "completion_tokens": 20},
    }
    (tmp_path / f"{key}.json").write_text(json.dumps({"body": body, "latency_s": 1.5}))

    prediction = asyncio.run(run_ai(request, ai_module, tmp_path))
    assert prediction.cached is True
    assert prediction.labels == {"importance": [("critical", 0.9)]}
    assert prediction.prompt_tokens == 120
    assert prediction.latency_s == 1.5


def test_combine_lets_regex_outrank_ai_and_applies_thresholds():
    taxonomy = load_taxonomy(FIX / "eval_taxonomy.json")
    regex = _prediction({"importance": [("normal", 0.6)]})
    ai = _prediction({"importance": [("critical", 0.95)], "stream": [("2025", 0.8), ("2026", 0.4)]})
    merged = combine(regex, ai, taxonomy, regex_threshold=0.6, ai_threshold=0.6)
    assert merged.labels["importance"] == [("normal", 0.6)]
    assert merged.labels["stream"] == [("2025", 0.8)]


def test_combine_single_keeps_one_value():
    taxonomy = load_taxonomy(FIX / "eval_taxonomy.json")
    ai = _prediction({"importance": [("normal", 0.7), ("critical", 0.9)]})
    merged = combine(_prediction({}), ai, taxonomy)
    assert merged.labels["importance"] == [("critical", 0.9)]


def test_combine_drops_regex_below_its_threshold_and_falls_back_to_ai():
    taxonomy = load_taxonomy(FIX / "eval_taxonomy.json")
    regex = _prediction({"importance": [("normal", 0.5)]})
    ai = _prediction({"importance": [("critical", 0.8)]})
    merged = combine(regex, ai, taxonomy, regex_threshold=0.6, ai_threshold=0.6)
    assert merged.labels["importance"] == [("critical", 0.8)]
