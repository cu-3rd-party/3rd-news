from datetime import UTC, datetime

import pytest
from joserfc.jwk import OKPKey
from pydantic import ValidationError

from thirdnews_contracts import (
    ClaimMismatchError,
    ClassificationError,
    ClassificationStatus,
    ClassifyResponse,
    IngestClient,
    IngestStatus,
    NewsBatchRequest,
    NewsSubmission,
    ReplayError,
    sign_message,
    verify_message,
)


def test_submission_requires_stable_identity() -> None:
    with pytest.raises(ValidationError):
        NewsSubmission(body_md="same text")
    item = NewsSubmission(body_md="same text", idempotency_key="producer-run-1")
    assert item.idempotency_key == "producer-run-1"


def test_ingest_client_uses_the_server_api_key_header() -> None:
    client = IngestClient("http://api:8000", "tn2_test")
    assert client.headers == {"X-API-Key": "tn2_test"}


def test_source_identity_requires_both_parts() -> None:
    with pytest.raises(ValidationError):
        NewsSubmission(body_md="x", source="rss")
    item = NewsSubmission(body_md="x", source="rss", external_id="guid")
    assert item.source == "rss"


@pytest.mark.parametrize(
    "changes",
    [
        {"body_md": "private-marker\x00"},
        {"title": "forged\x7flog"},
        {"extra": {"nested": "bad\x01value"}},
        {"labels": {"bad\x00facet": ["value"]}},
    ],
)
def test_submission_rejects_database_and_log_control_characters(
    changes: dict[str, object],
) -> None:
    payload = {"body_md": "line one\nline two\tvalue", "idempotency_key": "safe", **changes}
    with pytest.raises(ValidationError, match="forbidden control character"):
        NewsSubmission.model_validate(payload)


def test_submission_allows_structured_whitespace() -> None:
    item = NewsSubmission(body_md="line one\nline two\tvalue\r\n", idempotency_key="safe")
    assert "\n" in item.body_md


def test_batch_limit_is_enforced() -> None:
    item = NewsSubmission(body_md="x", idempotency_key="key")
    with pytest.raises(ValidationError):
        NewsBatchRequest(items=[item] * 201)


def test_batch_retains_a_malformed_object_for_per_item_rejection() -> None:
    batch = NewsBatchRequest.model_validate(
        {
            "items": [
                {"source": "rss", "external_id": "1", "body_md": "ok"},
                {"source": "rss", "body_md": "missing external id"},
            ]
        }
    )
    assert isinstance(batch.items[0], NewsSubmission)
    malformed = batch.items[1]
    assert isinstance(malformed, dict)
    assert malformed["body_md"] == "missing external id"


def test_signature_binds_body_and_routing_claims() -> None:
    key = OKPKey.generate_key("Ed25519")
    token = sign_message(
        key,
        b'{"ok":true}',
        issuer="thirdnews",
        audience="thirdnews-classifier",
        job_id="job",
        attempt_id="attempt",
        node_id="classifier-ai",
        now=100,
    )
    claims = verify_message(
        key.as_dict(private=False),
        token,
        b'{"ok":true}',
        issuer="thirdnews",
        audience="thirdnews-classifier",
        job_id="job",
        attempt_id="attempt",
        node_id="classifier-ai",
        now=101,
    )
    assert claims.job_id == "job"
    with pytest.raises(ClaimMismatchError):
        verify_message(
            key.as_dict(private=False),
            token,
            b'{"ok":false}',
            issuer="thirdnews",
            audience="thirdnews-classifier",
            job_id="job",
            attempt_id="attempt",
            node_id="classifier-ai",
            now=101,
        )


def test_replay_guard_rejects_second_use() -> None:
    key = OKPKey.generate_key("Ed25519")
    token = sign_message(
        key,
        b"{}",
        issuer="i",
        audience="a",
        job_id="j",
        attempt_id="x",
        node_id="n",
        now=100,
    )
    seen: set[str] = set()

    def guard(token_id: str, expires_at: int) -> bool:
        _ = expires_at
        if token_id in seen:
            return False
        seen.add(token_id)
        return True

    verify_message(
        key.as_dict(private=False),
        token,
        b"{}",
        replay_guard=guard,
        issuer="i",
        audience="a",
        job_id="j",
        attempt_id="x",
        node_id="n",
        now=101,
    )
    with pytest.raises(ReplayError):
        verify_message(
            key.as_dict(private=False),
            token,
            b"{}",
            replay_guard=guard,
            issuer="i",
            audience="a",
            job_id="j",
            attempt_id="x",
            node_id="n",
            now=101,
        )


def test_status_wire_value_is_v2() -> None:
    assert IngestStatus.ACCEPTED.value == "accepted"
    assert datetime.now(UTC).tzinfo is UTC


def _classification_response(**changes: object) -> dict[str, object]:
    response: dict[str, object] = {
        "request_id": "request",
        "job_id": "job",
        "attempt_id": "attempt",
        "news_id": "news",
        "news_version": 1,
        "classifier": "classifier-ai",
        "node_id": "classifier-ai",
        "status": "completed",
    }
    response.update(changes)
    return response


def test_failed_classification_requires_structured_error_and_no_labels() -> None:
    failed = ClassifyResponse.model_validate(
        _classification_response(
            status=ClassificationStatus.FAILED,
            error=ClassificationError(
                code="provider_error",
                message="provider unavailable",
                retryable=True,
            ),
        )
    )
    assert failed.status is ClassificationStatus.FAILED
    assert failed.error is not None and failed.error.retryable

    with pytest.raises(ValidationError, match="requires error"):
        ClassifyResponse.model_validate(_classification_response(status="failed"))


def test_classification_status_is_required_on_the_wire() -> None:
    response = _classification_response()
    response.pop("status")
    with pytest.raises(ValidationError, match="status"):
        ClassifyResponse.model_validate(response)


def test_completed_classification_rejects_error() -> None:
    with pytest.raises(ValidationError, match="cannot contain error"):
        ClassifyResponse.model_validate(
            _classification_response(
                error={
                    "code": "provider_error",
                    "message": "provider unavailable",
                    "retryable": True,
                }
            )
        )
