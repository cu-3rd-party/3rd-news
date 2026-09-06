from __future__ import annotations

import json
from typing import Any, cast

import pytest
from lib.infra.clients.classifier import ClassifierClient
from lib.infra.clients.http import FetchResult
from lib.interactor.errors.fetch_limit import FetchLimitError
from thirdnews_contracts import ClassifyNews, ClassifyRequest, Taxonomy


def request() -> ClassifyRequest:
    return ClassifyRequest(
        request_id="request-1",
        job_id="job-1",
        attempt_id="attempt-1",
        news=ClassifyNews(id="news-1", version=3, body_md="private body"),
        taxonomy=Taxonomy(version="1", facets=[]),
    )


def response_body() -> bytes:
    return json.dumps(
        {
            "contract_version": "2.0",
            "request_id": "request-1",
            "job_id": "job-1",
            "attempt_id": "attempt-1",
            "news_id": "news-1",
            "news_version": 3,
            "classifier": "qa",
            "node_id": "qa-node",
            "status": "completed",
            "labels": [],
        }
    ).encode()


@pytest.mark.asyncio
async def test_classifier_request_uses_the_bounded_pinned_post_interface(monkeypatch) -> None:
    class RecordingFetcher:
        validated: str | None = None
        posted: tuple[str, bytes, dict[str, str], int] | None = None

        async def validate_url(self, url: str):
            self.validated = url
            return ("192.0.2.10",)

        async def post_bytes(self, url, body, *, headers, max_bytes):
            self.posted = (url, body, headers, max_bytes)
            payload = response_body()
            return FetchResult(url, 200, "application/json", len(payload), payload)

    monkeypatch.setattr(
        "lib.infra.clients.classifier.client.sign_message",
        lambda *args, **kwargs: "signed-request",
    )
    fetcher = RecordingFetcher()
    client = ClassifierClient(
        private_key="unused by patched signer",
        issuer="qa",
        audience="classifier",
        node_id="qa-node",
        url_validator=cast(Any, fetcher),
        response_max_bytes=17,
    )

    dispatch = await client.classify("http://classifier.internal/", request())

    assert fetcher.validated == "http://classifier.internal/classify"
    assert fetcher.posted is not None
    url, body, headers, limit = fetcher.posted
    assert url == fetcher.validated
    assert json.loads(body) == request().model_dump(mode="json", exclude_none=True)
    assert headers["Authorization"] == "Bearer signed-request"
    assert headers["Content-Type"] == "application/json"
    assert limit == 17
    assert dispatch.response is not None
    assert dispatch.response.news_version == 3


@pytest.mark.asyncio
async def test_oversized_classifier_response_fails_without_a_second_transport(monkeypatch) -> None:
    class RejectingFetcher:
        calls = 0

        async def validate_url(self, url: str):
            return ("192.0.2.10",)

        async def post_bytes(self, url, body, *, headers, max_bytes):
            del url, body, headers
            self.calls += 1
            assert max_bytes == 5
            raise FetchLimitError("response exceeds limit 5")

    monkeypatch.setattr(
        "lib.infra.clients.classifier.client.sign_message",
        lambda *args, **kwargs: "signed-request",
    )
    fetcher = RejectingFetcher()
    client = ClassifierClient(
        private_key="unused by patched signer",
        issuer="qa",
        audience="classifier",
        node_id="qa-node",
        url_validator=cast(Any, fetcher),
        response_max_bytes=5,
    )

    with pytest.raises(FetchLimitError, match="limit 5"):
        await client.classify("http://classifier.internal", request())
    assert fetcher.calls == 1
