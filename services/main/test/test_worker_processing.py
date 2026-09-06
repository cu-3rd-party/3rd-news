from __future__ import annotations

import base64

from lib.interactor.use_cases.processing.classification_response_policy import (
    ClassificationResponsePolicy,
)
from lib.interactor.use_cases.processing.normalization import AxisDefinition, normalize_labels
from lib.interactor.use_cases.processing.raw_payloads import RawPayloadProtector
from lib.interactor.use_cases.processing.scoring import EditorialScores, evaluate_scores
from thirdnews_contracts import (
    ClassificationError,
    ClassificationStatus,
    ClassifyResponse,
)


def test_normalization_enforces_dynamic_axes_values_and_cardinality() -> None:
    axes = {
        "topic": AxisDefinition("topic", frozenset({"study", "sport"})),
        "campus": AxisDefinition("campus", frozenset({"north", "south"}), multiple=True),
    }
    labels = [
        {"axis": "unknown", "value": "x", "confidence": 1},
        {"axis": "topic", "value": "invented", "confidence": 1},
        {"axis": "topic", "value": "sport", "confidence": 0.8},
        {"axis": "topic", "value": "study", "confidence": 0.8},
        {"axis": "campus", "value": "north", "confidence": 0.9},
        {"axis": "campus", "value": "south", "confidence": float("nan")},
    ]

    result = normalize_labels(labels, axes=axes, allowed_axes=axes, min_confidence=0.5)

    assert [(label.axis, label.value) for label in result] == [
        ("campus", "north"),
        ("topic", "sport"),
    ]


def test_normalization_drops_axes_outside_classifier_registration() -> None:
    axes = {
        "topic": AxisDefinition("topic", frozenset({"study"})),
        "campus": AxisDefinition("campus", frozenset({"north"})),
    }
    result = normalize_labels(
        [
            {"axis": "topic", "value": "study", "confidence": 1},
            {"axis": "campus", "value": "north", "confidence": 1},
        ],
        axes=axes,
        allowed_axes=["topic"],
    )
    assert [(label.axis, label.value) for label in result] == [("topic", "study")]


def test_versioned_score_rules_start_neutral_and_clamp() -> None:
    scores = evaluate_scores(
        {"topic": ["emergency"], "audience": ["all"]},
        [
            {
                "id": "later",
                "priority": 20,
                "when": {"audience": ["all"]},
                "add": {"impact": 80},
            },
            {
                "id": "first",
                "priority": 10,
                "when": {"topic": "emergency"},
                "set": {"urgency": 95},
            },
        ],
    )
    assert scores == EditorialScores(urgency=95, impact=80, editorial_priority=0)
    assert scores.importance == 175


def test_failed_classifier_response_is_never_applicable() -> None:
    response = ClassifyResponse(
        request_id="request",
        job_id="job",
        attempt_id="attempt",
        news_id="news",
        news_version=1,
        classifier="ai",
        node_id="ai",
        status=ClassificationStatus.FAILED,
        error=ClassificationError(
            code="provider_error",
            message="provider unavailable",
            retryable=False,
        ),
    )

    failure = ClassificationResponsePolicy().failure(response)
    assert failure is not None
    error, retryable = failure
    assert str(error) == "classifier_failed:provider_error"
    assert retryable is False


def test_raw_audit_payload_is_authenticated_and_encrypted() -> None:
    protector = RawPayloadProtector(base64.urlsafe_b64encode(b"k" * 32).decode())
    raw = b'{"body_md":"sensitive news"}'
    encrypted = protector.encrypt(raw)
    assert raw not in encrypted
    assert protector.decrypt(encrypted) == raw

    changed = bytearray(encrypted)
    changed[-1] ^= 1
    try:
        protector.decrypt(bytes(changed))
    except Exception:
        pass
    else:
        raise AssertionError("tampering must be rejected")
