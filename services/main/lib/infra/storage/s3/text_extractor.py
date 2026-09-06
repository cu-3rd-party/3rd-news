from __future__ import annotations

import asyncio
import io
import json
import re
import sys
import zipfile
from contextlib import suppress
from typing import Any, cast
from xml.etree import ElementTree

from lib.core.config import (
    DOCX_COMPRESSION_METHODS,
    DOCX_COMPRESSION_RATIO_MAX,
    DOCX_CONTENT_TYPE,
    DOCX_READ_CHUNK_BYTES,
    DOCX_XML_MAX_BYTES,
    PDF_BOUNDED_FILTER_ATTRIBUTES,
    PDF_PAGE_MAX_COUNT,
    PDF_STREAM_MAX_BYTES,
    TEXT_ATTACHMENT_TYPES,
    TEXT_EXTRACTION_CHARACTER_MAX,
    TEXT_EXTRACTION_ERROR_MAX_BYTES,
    TEXT_EXTRACTION_HEADER_MAX_BYTES,
    TEXT_EXTRACTION_INPUT_MAX_BYTES,
    TEXT_EXTRACTION_IO_CHUNK_BYTES,
    TEXT_EXTRACTION_OUTPUT_MAX_BYTES_PER_CHARACTER,
    TEXT_EXTRACTION_TIMEOUT_SECONDS,
)
from lib.infra.storage.s3.visible_text_parser import VisibleTextParser


async def extract_text_isolated(
    data: bytes,
    *,
    content_type: str | None,
    filename: str | None = None,
    max_characters: int = TEXT_EXTRACTION_CHARACTER_MAX,
    timeout_seconds: float = TEXT_EXTRACTION_TIMEOUT_SECONDS,
) -> str | None:

    if len(data) > TEXT_EXTRACTION_INPUT_MAX_BYTES:
        raise ValueError("attachment exceeds the text-extraction input limit")
    if not 1 <= max_characters <= TEXT_EXTRACTION_CHARACTER_MAX:
        raise ValueError("max_characters is outside the text-extraction limit")
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "lib.infra.storage.s3.text_extractor_worker",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    if process.stdin is None or process.stdout is None or process.stderr is None:
        await stop_extractor(process)
        raise RuntimeError("text-extraction subprocess pipes are unavailable")
    header = json.dumps(
        {
            "content_type": content_type,
            "filename": filename,
            "max_characters": max_characters,
        },
        separators=(",", ":"),
    ).encode()
    if len(header) + 1 > TEXT_EXTRACTION_HEADER_MAX_BYTES:
        await stop_extractor(process)
        raise ValueError("text-extraction request metadata exceeds its limit")
    tasks = (
        asyncio.create_task(write_extractor_input(process.stdin, header + b"\n" + data)),
        asyncio.create_task(
            read_extractor_output(
                process.stdout,
                max_characters * TEXT_EXTRACTION_OUTPUT_MAX_BYTES_PER_CHARACTER,
            )
        ),
        asyncio.create_task(read_extractor_output(process.stderr, TEXT_EXTRACTION_ERROR_MAX_BYTES)),
        asyncio.create_task(process.wait()),
    )
    try:
        async with asyncio.timeout(timeout_seconds):
            _, stdout, _, return_code = await asyncio.gather(*tasks)
    except BaseException:
        await stop_extractor(process)
        await asyncio.gather(*tasks, return_exceptions=True)
        raise
    if return_code != 0:
        raise ValueError(f"text extraction failed in isolated process (exit {return_code})")
    try:
        text = stdout.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("text extraction returned invalid UTF-8") from exc
    return text or None


async def write_extractor_input(writer: asyncio.StreamWriter, data: bytes) -> None:
    try:
        view = memoryview(data)
        for offset in range(0, len(view), TEXT_EXTRACTION_IO_CHUNK_BYTES):
            writer.write(view[offset : offset + TEXT_EXTRACTION_IO_CHUNK_BYTES])
            await writer.drain()
    except BrokenPipeError, ConnectionResetError:
        pass
    finally:
        writer.close()
        wait_closed = asyncio.create_task(writer.wait_closed())
        try:
            with suppress(BrokenPipeError, ConnectionResetError):
                await asyncio.shield(wait_closed)
        except asyncio.CancelledError:
            with suppress(BrokenPipeError, ConnectionResetError):
                await wait_closed
            raise


async def read_extractor_output(reader: asyncio.StreamReader, limit: int) -> bytes:
    output = bytearray()
    while chunk := await reader.read(TEXT_EXTRACTION_IO_CHUNK_BYTES):
        output.extend(chunk)
        if len(output) > limit:
            raise ValueError("text-extraction subprocess output exceeds its limit")
    return bytes(output)


async def stop_extractor(process: asyncio.subprocess.Process) -> None:
    if process.returncode is not None:
        return
    with suppress(ProcessLookupError):
        process.kill()
    await process.wait()


def extract_text(
    data: bytes,
    *,
    content_type: str | None,
    filename: str | None = None,
    max_characters: int = TEXT_EXTRACTION_CHARACTER_MAX,
) -> str | None:

    if not 1 <= max_characters <= TEXT_EXTRACTION_CHARACTER_MAX:
        raise ValueError("max_characters is outside the text-extraction limit")
    mime = (content_type or "").split(";", 1)[0].strip().lower()
    suffix = (filename or "").lower().rsplit(".", 1)[-1]
    if mime.startswith(("image/", "audio/", "video/")):
        return None
    if mime == "application/pdf" or suffix == "pdf":
        text = _pdf(data, max_characters=max_characters)
    elif mime == DOCX_CONTENT_TYPE or suffix == "docx":
        text = _docx(data)
    elif (
        mime in TEXT_ATTACHMENT_TYPES
        or mime.startswith("text/")
        or suffix in {"txt", "md", "csv", "json", "xml", "html", "htm"}
    ):
        decoded = _decode(data)
        if mime == "text/html" or suffix in {"html", "htm"}:
            parser = VisibleTextParser()
            parser.feed(decoded)
            text = "\n".join(parser.parts)
        elif mime == "application/json" or suffix == "json":
            try:
                text = json.dumps(json.loads(decoded), ensure_ascii=False, indent=2)
            except ValueError:
                text = decoded
        else:
            text = decoded
    else:
        return None
    normalized = re.sub(r"[\t\x0b\x0c\r ]+", " ", text)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized).strip()
    return normalized[:max_characters] or None


def _decode(data: bytes) -> str:
    if data.startswith(b"\xef\xbb\xbf"):
        return data.decode("utf-8-sig", errors="replace")
    for encoding in ("utf-8", "utf-16", "cp1251"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _pdf(data: bytes, *, max_characters: int) -> str:
    try:
        from pypdf import PdfReader, filters
    except ImportError as exc:
        raise RuntimeError("pypdf is required for PDF text extraction") from exc
    pdf_filters = cast(Any, filters)
    for attribute in PDF_BOUNDED_FILTER_ATTRIBUTES:
        setattr(pdf_filters, attribute, PDF_STREAM_MAX_BYTES)
    reader = PdfReader(io.BytesIO(data), strict=False)
    if len(reader.pages) > PDF_PAGE_MAX_COUNT:
        raise ValueError("PDF exceeds the page-count limit")
    remaining = max_characters
    parts: list[str] = []
    for page in reader.pages:
        text = page.extract_text() or ""
        parts.append(text[:remaining])
        remaining -= len(parts[-1])
        if remaining <= 0:
            break
    return "\n\n".join(parts)[:max_characters]


def _docx(data: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            info = archive.getinfo("word/document.xml")
            _validate_docx_member(info)
            document = _read_docx_member(archive, info)
    except (KeyError, NotImplementedError, RuntimeError, zipfile.BadZipFile) as exc:
        raise ValueError("invalid DOCX attachment") from exc
    try:
        root = ElementTree.fromstring(document)
    except ElementTree.ParseError as exc:
        raise ValueError("invalid DOCX document XML") from exc
    paragraphs: list[str] = []
    for paragraph in root.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p"):
        parts = [
            node.text or ""
            for node in paragraph.iter(
                "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t"
            )
        ]
        if parts:
            paragraphs.append("".join(parts))
    return "\n".join(paragraphs)


def _validate_docx_member(info: zipfile.ZipInfo) -> None:
    if info.is_dir() or info.flag_bits & 0x1:
        raise ValueError("encrypted or directory DOCX document member is not supported")
    if info.compress_type not in DOCX_COMPRESSION_METHODS:
        raise ValueError("unsupported DOCX compression method")
    if info.file_size > DOCX_XML_MAX_BYTES:
        raise ValueError("DOCX document XML exceeds the expanded-size limit")
    if info.file_size and not info.compress_size:
        raise ValueError("DOCX document XML has an invalid compressed size")
    if info.file_size / max(info.compress_size, 1) > DOCX_COMPRESSION_RATIO_MAX:
        raise ValueError("DOCX document XML exceeds the compression-ratio limit")


def _read_docx_member(archive: zipfile.ZipFile, info: zipfile.ZipInfo) -> bytes:
    document = bytearray()
    with archive.open(info, "r") as member:
        while chunk := member.read(DOCX_READ_CHUNK_BYTES):
            document.extend(chunk)
            if len(document) > DOCX_XML_MAX_BYTES:
                raise ValueError("DOCX document XML exceeds the streaming limit")
    if len(document) != info.file_size:
        raise ValueError("DOCX document XML size does not match ZIP metadata")
    return bytes(document)
