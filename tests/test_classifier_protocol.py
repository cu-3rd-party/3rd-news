"""HTTP-level test of the classifier protocol, over the real ASGI app.

This is the contract a third-party classifier has to satisfy, exercised end to
end: manifest, signature check, and a classify round trip.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from thirdnews_contracts import (
    ClassifyNews,
    ClassifyOptions,
    ClassifyRequest,
    ClassifyResponse,
    FacetSchema,
    FacetValueSchema,
    ProposedLabel,
    Taxonomy,
    sign_payload,
)
from thirdnews_contracts.worker import build_classifier_app

SECRET = "shared-secret"

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
        )
    ]
)


def build_app(secret: str | None = SECRET):
    def classify(request: ClassifyRequest) -> list[ProposedLabel]:
        return [ProposedLabel(facet="importance", value="high", confidence=0.8)]

    return build_classifier_app(
        slug="probe", name="Probe", classify=classify, secret=secret, facets=["importance"]
    )


def payload() -> bytes:
    request = ClassifyRequest(
        request_id="job-1",
        news=ClassifyNews(id="n1", body_md="дедлайн"),
        taxonomy=TAXONOMY,
        options=ClassifyOptions(),
    )
    return request.model_dump_json().encode()


@pytest.fixture()
def client():
    with TestClient(build_app()) as test_client:
        yield test_client


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_manifest_describes_the_service(client):
    manifest = client.get("/manifest").json()
    assert manifest["slug"] == "probe"
    assert manifest["facets"] == ["importance"]
    assert manifest["contract_version"] == "1.0"


def test_classify_returns_the_request_id_and_labels(client):
    body = payload()
    response = client.post(
        "/classify",
        content=body,
        headers={"Content-Type": "application/json", **sign_payload(SECRET, body)},
    )
    assert response.status_code == 200
    result = ClassifyResponse.model_validate(response.json())
    assert result.request_id == "job-1"
    assert result.classifier == "probe"
    assert [(label.facet, label.value) for label in result.labels] == [("importance", "high")]


def test_classify_rejects_a_missing_signature(client):
    response = client.post("/classify", content=payload())
    assert response.status_code == 401


def test_classify_rejects_a_signature_over_a_different_body(client):
    headers = sign_payload(SECRET, b"something else")
    response = client.post(
        "/classify",
        content=payload(),
        headers={"Content-Type": "application/json", **headers},
    )
    assert response.status_code == 401


def test_unsigned_service_accepts_unsigned_requests():
    with TestClient(build_app(secret=None)) as client:
        response = client.post("/classify", content=payload())
        assert response.status_code == 200


def test_malformed_body_is_a_validation_error(client):
    body = json.dumps({"nope": True}).encode()
    response = client.post(
        "/classify",
        content=body,
        headers={"Content-Type": "application/json", **sign_payload(SECRET, body)},
    )
    assert response.status_code == 422
