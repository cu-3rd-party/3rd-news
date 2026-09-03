"""Tests for the public contracts: signing and submission validation."""

from __future__ import annotations

import time

import pytest
from pydantic import ValidationError
from thirdnews_contracts import (
    AttachmentInput,
    AttachmentKind,
    NewsSubmission,
    sign_payload,
    verify_signature,
)
from thirdnews_contracts.signing import SIGNATURE_HEADER, TIMESTAMP_HEADER

SECRET = "s3cret"


def test_signature_round_trip():
    body = b'{"hello":"world"}'
    headers = sign_payload(SECRET, body)
    assert verify_signature(
        SECRET, body, headers[SIGNATURE_HEADER], headers[TIMESTAMP_HEADER]
    )


def test_signature_rejects_tampered_body():
    body = b'{"hello":"world"}'
    headers = sign_payload(SECRET, body)
    assert not verify_signature(
        SECRET, b'{"hello":"evil"}', headers[SIGNATURE_HEADER], headers[TIMESTAMP_HEADER]
    )


def test_signature_rejects_wrong_secret():
    body = b"payload"
    headers = sign_payload(SECRET, body)
    assert not verify_signature(
        "other", body, headers[SIGNATURE_HEADER], headers[TIMESTAMP_HEADER]
    )


def test_signature_rejects_stale_timestamp():
    body = b"payload"
    old = int(time.time()) - 10_000
    headers = sign_payload(SECRET, body, timestamp=old)
    assert not verify_signature(
        SECRET, body, headers[SIGNATURE_HEADER], headers[TIMESTAMP_HEADER]
    )


def test_signature_rejects_missing_headers():
    assert not verify_signature(SECRET, b"payload", None, None)


def test_submission_requires_attribution():
    with pytest.raises(ValidationError):
        NewsSubmission(body_md="текст без источника")


def test_submission_accepts_source_text_only():
    submission = NewsSubmission(body_md="текст", source_text="Деканат ФКН")
    assert submission.source_text == "Деканат ФКН"
    assert submission.published_at is None


def test_attachment_needs_exactly_one_source():
    with pytest.raises(ValidationError):
        AttachmentInput(kind=AttachmentKind.IMAGE)
    with pytest.raises(ValidationError):
        AttachmentInput(
            kind=AttachmentKind.IMAGE, url="https://e.edu/a.jpg", upload_name="a"
        )
    AttachmentInput(kind=AttachmentKind.IMAGE, url="https://e.edu/a.jpg")
    AttachmentInput(kind=AttachmentKind.IMAGE, upload_name="cover")
