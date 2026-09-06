from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast

import pytest
from lib.dto.accepted_submission import AcceptedSubmission
from lib.dto.requests import ClassifierPatch, NewsEdit
from lib.handlers import admin_classifiers, submissions
from lib.infra.clients.auth import Principal
from pydantic import ValidationError


@pytest.mark.asyncio
async def test_news_endpoint_accepts_header_only_idempotency(monkeypatch) -> None:
    captured = None

    class Service:
        async def execute(self, payload, **kwargs):
            nonlocal captured
            captured = payload
            return AcceptedSubmission(uuid.uuid4(), "accepted", datetime.now(UTC))

    monkeypatch.setattr(submissions, "ingest_service", lambda request: Service())
    principal = Principal("api_key", "parser", "Parser", frozenset({"ingest"}))
    result = await submissions.submit_news(
        request=cast(Any, SimpleNamespace()),
        principal=principal,
        payload={"body_md": "Header identity"},
        idempotency_key="header-only-key",
    )

    assert captured is not None
    assert captured.idempotency_key == "header-only-key"
    assert result.status == "accepted"


def test_news_edit_rejects_null_body_and_extra() -> None:
    for field in ("body_md", "extra"):
        with pytest.raises(ValidationError, match=f"{field} cannot be null"):
            NewsEdit.model_validate({field: None})


def test_classifier_patch_omits_signing_key_and_unset_fields() -> None:
    payload = ClassifierPatch.model_validate({"enabled": False})

    assert admin_classifiers.classifier_patch_values(payload) == {"enabled": False}


@pytest.mark.asyncio
async def test_classifier_probe_does_not_trust_registered_endpoint_host(
    monkeypatch,
) -> None:
    recorded: list[str | None] = []

    class Repository:
        async def classifier_probe_target(self, classifier_id):
            return "http://127.0.0.1:9", 1.0

        async def record_classifier_probe(self, classifier_id, error):
            recorded.append(error)

    monkeypatch.setattr(admin_classifiers, "classifier_storage", lambda session: Repository())
    settings = SimpleNamespace(
        classifier_service_hosts=[],
        fetch_max_redirects=0,
        classifier_request_timeout_seconds=1.0,
        classifier_response_max_bytes=1024,
    )
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(settings=settings)))
    principal = Principal("user", "admin", "Admin", frozenset({"admin"}))

    result = await admin_classifiers.probe_classifier(
        uuid.uuid4(), cast(Any, request), cast(Any, object()), principal
    )

    assert result == {"ok": False, "error": "SsrfBlockedError"}
    assert recorded == ["SsrfBlockedError"]
