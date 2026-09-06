from __future__ import annotations

import asyncio
import io
import math
import struct
import zipfile
from typing import Any, cast

import pytest
from lib.core.config import (
    DOCX_XML_MAX_BYTES,
    PDF_BOUNDED_FILTER_ATTRIBUTES,
    PDF_PAGE_MAX_COUNT,
    PDF_STREAM_MAX_BYTES,
)
from lib.infra.clients.http import SafeFetcher, UrlPolicy
from lib.infra.clients.nats.outbox import OutboxPublisher
from lib.infra.storage.s3 import (
    S3ObjectStore,
    extract_text,
    extract_text_isolated,
    parse_range_header,
    text_extractor,
)
from lib.interactor.errors.fetch_limit import FetchLimitError
from lib.interactor.errors.ssrf_blocked import SsrfBlockedError


@pytest.mark.asyncio
async def test_url_fetch_rejects_private_or_mixed_dns_answers() -> None:
    async def private(_: str, __: int) -> list[str]:
        return ["127.0.0.1"]

    fetcher = SafeFetcher(resolver=private)
    with pytest.raises(SsrfBlockedError):
        await fetcher.validate_url("http://example.test/file")

    async def mixed(_: str, __: int) -> list[str]:
        return ["93.184.216.34", "10.0.0.2"]

    fetcher = SafeFetcher(resolver=mixed)
    with pytest.raises(SsrfBlockedError):
        await fetcher.validate_url("https://example.test/file")


@pytest.mark.asyncio
async def test_registered_internal_adapter_is_explicitly_allowed() -> None:
    async def internal(_: str, __: int) -> list[str]:
        return ["10.0.0.2"]

    fetcher = SafeFetcher(
        resolver=internal,
        policy=UrlPolicy.with_service_hosts(["classifier.internal"]),
    )
    assert await fetcher.validate_url("http://classifier.internal/classify") == ("10.0.0.2",)


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("bytes=0-9", (0, 9)),
        ("bytes=10-", (10, 99)),
        ("bytes=-10", (90, 99)),
        (None, None),
    ],
)
def test_media_range_parser(header: str | None, expected: tuple[int, int] | None) -> None:
    parsed = parse_range_header(header, 100)
    assert ((parsed.start, parsed.end) if parsed else None) == expected


@pytest.mark.parametrize("header", ["items=0-1", "bytes=100-101", "bytes=9-2", "bytes=-0"])
def test_media_range_parser_rejects_invalid_or_unsatisfiable_ranges(header: str) -> None:
    with pytest.raises(ValueError):
        parse_range_header(header, 100)


def test_text_extraction_does_not_execute_or_retain_active_html() -> None:
    raw = b"<h1>Visible</h1><script>alert('secret')</script><p>Body</p>"
    assert extract_text(raw, content_type="text/html") == "Visible\nBody"
    assert extract_text(b"pixels", content_type="image/png") is None


def test_outbox_rejects_news_text_and_secrets() -> None:
    with pytest.raises(ValueError):
        OutboxPublisher._validate_event("submission.accepted.v2", {"body_md": "private"})
    with pytest.raises(ValueError):
        OutboxPublisher._validate_event("submission.accepted.v2", {"nested": {"secret": "x"}})
    OutboxPublisher._validate_event(
        "submission.accepted.v2", {"submission_id": "123", "revision": 2}
    )


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_outbox_rejects_non_finite_json_numbers(value: float) -> None:
    with pytest.raises(ValueError, match="non-finite"):
        OutboxPublisher._validate_event("submission.accepted.v2", {"revision": value})


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://example.test/file",
        "http://user:password@example.test/file",
        "http://example.test:99999/file",
    ],
)
@pytest.mark.asyncio
async def test_url_fetch_rejects_unsafe_url_syntax_before_connect(url: str) -> None:
    async def public(_: str, __: int) -> list[str]:
        return ["93.184.216.34"]

    with pytest.raises(SsrfBlockedError):
        await SafeFetcher(resolver=public).validate_url(url)


@pytest.mark.asyncio
async def test_chunked_classifier_response_is_bounded_without_content_length() -> None:
    class ChunkedBody:
        async def iter_chunked(self, size):
            del size
            yield b"123"
            yield b"456"

    class Response:
        headers = {}
        content = ChunkedBody()

    fetcher = SafeFetcher(max_bytes=5)
    with pytest.raises(FetchLimitError, match="response exceeds limit 5"):
        await fetcher._read_bounded(cast(Any, Response()), 5)


def test_content_disposition_strips_path_and_header_characters() -> None:
    store = object.__new__(S3ObjectStore)
    value = store.content_disposition('../../отчёт\r\n".pdf')
    assert ".." not in value
    assert "\r" not in value and "\n" not in value
    assert "filename*=UTF-8''" in value


@pytest.mark.asyncio
async def test_presigned_upload_uses_public_endpoint() -> None:
    store = S3ObjectStore(
        endpoint_url="http://file:3900",
        public_endpoint_url="https://uploads.example.test",
        bucket="test",
        access_key="access",
        secret_key="secret",
    )
    upload = await store.create_upload(
        owner_id="owner",
        intent_id="intent",
        size=3,
        content_type="text/plain",
        sha256="a" * 64,
    )
    assert upload.url.startswith("https://uploads.example.test/test/tmp/")


def test_docx_extraction_reads_bounded_document_xml() -> None:
    document = (
        b'<w:document xmlns:w="http://schemas.openxmlformats.org/'
        b'wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>'
        b"Visible text"
        b"</w:t></w:r></w:p></w:body></w:document>"
    )
    archive_bytes = io.BytesIO()
    with zipfile.ZipFile(archive_bytes, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("word/document.xml", document)

    assert extract_text(archive_bytes.getvalue(), content_type=None, filename="safe.docx") == (
        "Visible text"
    )


def test_docx_extraction_rejects_excessive_compression_ratio() -> None:
    document = b"<w:document>" + b" " * 1_000_000 + b"</w:document>"
    archive_bytes = io.BytesIO()
    with zipfile.ZipFile(archive_bytes, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("word/document.xml", document)

    with pytest.raises(ValueError, match="compression-ratio"):
        extract_text(archive_bytes.getvalue(), content_type=None, filename="bomb.docx")


def test_docx_extraction_rejects_oversized_declared_member() -> None:
    archive_bytes = io.BytesIO()
    with zipfile.ZipFile(archive_bytes, "w", zipfile.ZIP_STORED) as archive:
        archive.writestr("word/document.xml", b"<w:document/>")
    raw = bytearray(archive_bytes.getvalue())
    central_directory = raw.index(b"PK\x01\x02")
    struct.pack_into("<I", raw, central_directory + 24, DOCX_XML_MAX_BYTES + 1)

    with pytest.raises(ValueError, match="expanded-size"):
        extract_text(bytes(raw), content_type=None, filename="lying.docx")


def test_docx_streaming_limit_rejects_member_larger_than_metadata() -> None:
    class Member:
        def __init__(self) -> None:
            self.remaining = DOCX_XML_MAX_BYTES + 1

        def __enter__(self) -> Member:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self, size: int) -> bytes:
            chunk_size = min(size, self.remaining)
            self.remaining -= chunk_size
            return b"x" * chunk_size

    class Archive:
        def open(self, info: zipfile.ZipInfo, mode: str) -> Member:
            del info, mode
            return Member()

    info = zipfile.ZipInfo("word/document.xml")
    info.file_size = 1
    with pytest.raises(ValueError, match="streaming limit"):
        text_extractor._read_docx_member(cast(Any, Archive()), info)


def test_pdf_extraction_applies_bounded_decoder_limits() -> None:
    from pypdf import PdfWriter, filters

    output = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.write(output)

    assert extract_text(output.getvalue(), content_type="application/pdf") is None
    for attribute in PDF_BOUNDED_FILTER_ATTRIBUTES:
        assert getattr(filters, attribute) == PDF_STREAM_MAX_BYTES


def test_pdf_extraction_rejects_excessive_page_count() -> None:
    from pypdf import PdfWriter

    output = io.BytesIO()
    writer = PdfWriter()
    for _ in range(PDF_PAGE_MAX_COUNT + 1):
        writer.add_blank_page(width=1, height=1)
    writer.write(output)

    with pytest.raises(ValueError, match="page-count"):
        extract_text(output.getvalue(), content_type="application/pdf")


@pytest.mark.asyncio
async def test_isolated_text_extraction_returns_plain_text() -> None:
    assert (
        await extract_text_isolated(
            "Привет из вложения".encode(),
            content_type="text/plain",
            filename="note.txt",
        )
        == "Привет из вложения"
    )


@pytest.mark.asyncio
async def test_isolated_text_extraction_kills_process_on_timeout() -> None:
    loop = asyncio.get_running_loop()
    previous_handler = loop.get_exception_handler()
    loop_errors: list[dict[str, Any]] = []
    loop.set_exception_handler(lambda _loop, context: loop_errors.append(context))
    try:
        with pytest.raises(TimeoutError):
            await extract_text_isolated(
                b"bounded",
                content_type="text/plain",
                filename="--looks-like-an-option.txt",
                timeout_seconds=1e-9,
            )
        await asyncio.sleep(0.05)
    finally:
        loop.set_exception_handler(previous_handler)
    assert loop_errors == []


@pytest.mark.asyncio
async def test_isolated_text_extraction_maps_parser_failure() -> None:
    with pytest.raises(ValueError, match="isolated process"):
        await extract_text_isolated(
            b"not a zip archive",
            content_type=(
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            ),
        )
