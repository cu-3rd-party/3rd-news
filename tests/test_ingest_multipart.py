"""Разбор multipart-запроса приёма новостей.

Тест на регрессию: `request.form()` отдаёт `starlette.datastructures.UploadFile`,
а `fastapi.UploadFile` — его наследник. Проверка `isinstance(value,
fastapi.UploadFile)` из-за этого всегда ложна, и вложения пропадали молча —
приём отвечал 200, новость создавалась, файлов не было. Ловится это только
настоящим multipart-запросом, поэтому здесь поднимается ASGI-приложение с
одной ручкой, повторяющей разбор из `app.routers.ingest`.
"""

from __future__ import annotations

import json

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from thirdnews_contracts import AttachmentInput, AttachmentKind, NewsSubmission

from app.routers.ingest import _read_request


@pytest.fixture()
def client() -> TestClient:
    app = FastAPI()

    @app.post("/ingest")
    async def ingest(request: Request) -> dict:
        submission, uploads = await _read_request(request)
        return {
            "external_id": submission.external_id,
            "attachments": [item.upload_name for item in submission.attachments],
            "uploads": {
                name: {"filename": filename, "size": len(data), "mime": mime}
                for name, (filename, data, mime) in uploads.items()
            },
        }

    return TestClient(app)


def submission_payload() -> str:
    submission = NewsSubmission(
        external_id="post-1",
        source_key="time-test",
        body_md="Текст анонса",
        attachments=[
            AttachmentInput(kind=AttachmentKind.IMAGE, upload_name="file_0", filename="афиша.png"),
            AttachmentInput(kind=AttachmentKind.PDF, upload_name="file_1", filename="программа.pdf"),
        ],
    )
    return json.dumps(submission.model_dump(mode="json", exclude_none=True))


def test_multipart_uploads_reach_the_handler(client):
    response = client.post(
        "/ingest",
        data={"payload": submission_payload()},
        files={
            "file_0": ("афиша.png", b"\x89PNG\r\n\x1a\n" + b"0" * 500, "image/png"),
            "file_1": ("программа.pdf", b"%PDF-1.4" + b"0" * 100, "application/pdf"),
        },
    )
    assert response.status_code == 200
    body = response.json()

    # Тот самый случай: раньше здесь приезжал пустой словарь.
    assert set(body["uploads"]) == {"file_0", "file_1"}
    assert body["uploads"]["file_0"]["mime"] == "image/png"
    assert body["uploads"]["file_0"]["size"] == 508
    assert body["uploads"]["file_1"]["filename"] == "программа.pdf"


def test_upload_names_line_up_with_the_declared_attachments(client):
    body = client.post(
        "/ingest",
        data={"payload": submission_payload()},
        files={"file_0": ("афиша.png", b"x", "image/png"),
               "file_1": ("программа.pdf", b"y", "application/pdf")},
    ).json()
    assert body["attachments"] == list(body["uploads"])


def test_json_request_still_works(client):
    payload = json.loads(submission_payload())
    payload["attachments"] = [
        {"kind": "image", "url": "https://example.edu/a.png"},
    ]
    body = client.post("/ingest", json=payload).json()
    assert body["uploads"] == {}
    assert body["external_id"] == "post-1"


def test_multipart_without_payload_field_is_rejected(client):
    response = client.post("/ingest", files={"file_0": ("a.png", b"x", "image/png")})
    assert response.status_code == 422
    assert "payload" in response.json()["detail"]


def test_broken_payload_json_is_rejected(client):
    response = client.post(
        "/ingest",
        data={"payload": "{не json"},
        files={"file_0": ("a.png", b"x", "image/png")},
    )
    assert response.status_code == 422
