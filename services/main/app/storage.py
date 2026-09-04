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
    """ASCII-имя для пути на диске.

    Расширение чистится отдельно и никогда не теряется: без него статика
    отдаётся как `application/octet-stream`, и картинка в браузере не
    открывается. Русское имя целиком превращается в подчёркивания, поэтому у
    `эрмитаж.png` от имени ничего не остаётся — тогда берётся `file`, но
    `.png` остаётся на месте. Человеческое имя при этом хранится отдельно,
    см. `display_filename`.
    """

    if not name:
        return f"{uuid.uuid4().hex}{fallback_ext}"

    path = Path(name.strip()).name
    suffix = _UNSAFE.sub("", Path(path).suffix)[:16]
    stem = _UNSAFE.sub("_", Path(path).stem).strip("._")
    return f"{(stem or 'file')[:180]}{suffix or fallback_ext}"


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


def display_filename(name: str | None) -> str | None:
    """Human-facing name, kept as the author wrote it.

    Only the path is stripped: "события август.png" must survive intact, since
    most of what this service stores is named in Russian. The ASCII-only form
    is used for the path on disk, never for what the reader sees.
    """

    if not name:
        return None
    cleaned = Path(name.strip()).name.replace("\x00", "").strip()
    return cleaned[:200] or None


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
        "filename": display_filename(filename) or name,
        "mime": mime or mimetypes.guess_type(name)[0],
        "size": len(data),
        "checksum": checksum,
    }


def public_url(storage_path: str | None) -> str | None:
    """Absolute URL of a stored attachment.

    A relative `/media/...` is useless to the clients that actually read this
    API — a bot, another site — so a relative `media_base_url` is resolved
    against the service's public address. Set `media_base_url` to a full URL
    to serve attachments from a CDN instead.
    """

    if not storage_path:
        return None
    base = settings.media_base_url.rstrip("/")
    path = storage_path.lstrip("/")
    if base.startswith("http://") or base.startswith("https://"):
        return f"{base}/{path}"
    return f"{settings.public_base_url.rstrip('/')}/{base.lstrip('/')}/{path}"
