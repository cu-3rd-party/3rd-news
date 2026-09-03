"""Attachment storage on a local volume.

Deliberately behind a tiny interface: swapping in S3/MinIO later means
reimplementing `save_bytes` / `public_url` and nothing else.
"""

from __future__ import annotations

import hashlib
import mimetypes
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .config import settings

_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")
#: Extensions we refuse to store regardless of the declared MIME type.
_BLOCKED_SUFFIXES = {".exe", ".dll", ".so", ".bat", ".cmd", ".com", ".scr", ".msi", ".sh"}


def safe_filename(name: str | None, fallback_ext: str = "") -> str:
    if not name:
        return f"{uuid.uuid4().hex}{fallback_ext}"
    cleaned = _UNSAFE.sub("_", Path(name).name).strip("._") or uuid.uuid4().hex
    return cleaned[:180]


def guess_kind(mime: str | None, filename: str | None) -> str:
    mime = mime or (mimetypes.guess_type(filename or "")[0] or "")
    if mime.startswith("image/"):
        return "image"
    if mime.startswith("video/"):
        return "video"
    if mime.startswith("audio/"):
        return "audio"
    if mime == "application/pdf" or (filename or "").lower().endswith(".pdf"):
        return "pdf"
    return "file"


def save_bytes(data: bytes, filename: str | None, mime: str | None) -> dict:
    """Write `data` under the media root; return the attachment metadata."""

    name = safe_filename(filename)
    if Path(name).suffix.lower() in _BLOCKED_SUFFIXES:
        raise ValueError(f"refusing to store executable attachment {name!r}")

    now = datetime.now(timezone.utc)
    rel_dir = Path(f"{now:%Y/%m}")
    checksum = hashlib.sha256(data).hexdigest()
    # Prefixing with the checksum makes repeated downloads idempotent and
    # keeps two different files with the same name apart.
    rel_path = rel_dir / f"{checksum[:16]}_{name}"

    target = settings.media_root / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        target.write_bytes(data)

    return {
        "storage_path": rel_path.as_posix(),
        "filename": name,
        "mime": mime or mimetypes.guess_type(name)[0],
        "size": len(data),
        "checksum": checksum,
    }


def public_url(storage_path: str | None) -> str | None:
    if not storage_path:
        return None
    return f"{settings.media_base_url.rstrip('/')}/{storage_path.lstrip('/')}"
