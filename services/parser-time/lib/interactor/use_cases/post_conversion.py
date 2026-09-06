import re
from datetime import UTC, datetime
from typing import Any

from pydantic import HttpUrl
from thirdnews_contracts import AttachmentKind, NewsSubmission

from ...domain.entities.channel_ref import ChannelRef
from ...domain.entities.post_rules import (
    EMOJI_SHORTCODE,
    EMPHASIS,
    EMPTY_MARKDOWN,
    LEADING_NOISE,
    MAX_TITLE_LEN,
    SYSTEM_POST_PREFIX,
)


def post_files(post: dict[str, Any]) -> list[dict[str, Any]]:
    metadata = post.get("metadata") or {}
    return [item for item in (metadata.get("files") or []) if isinstance(item, dict)]


def post_body(post: dict[str, Any]) -> str:
    parts: list[str] = []
    message = (post.get("message") or "").strip()
    if message:
        parts.append(message)
    props = post.get("props") or {}
    for attachment in props.get("attachments") or []:
        if not isinstance(attachment, dict):
            continue
        for field in ("pretext", "title", "text", "fallback"):
            value = (attachment.get(field) or "").strip()
            if value and value not in parts:
                parts.append(value)
                if field == "text":
                    break
    return "\n\n".join(parts).strip()


def is_newsworthy(post: dict[str, Any], include_replies: bool = False) -> bool:
    if post.get("delete_at"):
        return False
    if str(post.get("type", "")).startswith(SYSTEM_POST_PREFIX):
        return False
    if not include_replies and post.get("root_id"):
        return False
    return bool(post_body(post).strip()) or bool(post_files(post))


def guess_title(body: str) -> str | None:
    lines = [line for line in body.splitlines() if not EMPTY_MARKDOWN.match(line)]
    if len(lines) < 2:
        return None
    first = EMOJI_SHORTCODE.sub(" ", lines[0])
    first = EMPHASIS.sub("", first)
    first = LEADING_NOISE.sub("", first)
    first = re.sub(r"\s+", " ", first).strip().rstrip(" ,;:—–-")
    if not first or len(first) > MAX_TITLE_LEN:
        return None
    return first


def attachment_kind(mime: str | None, extension: str | None) -> AttachmentKind:
    normalized_mime = (mime or "").lower()
    normalized_extension = (extension or "").lower().lstrip(".")
    if normalized_mime.startswith("image/") or normalized_extension in {
        "png",
        "jpg",
        "jpeg",
        "gif",
        "webp",
        "svg",
    }:
        return AttachmentKind.IMAGE
    if normalized_mime.startswith("video/") or normalized_extension in {
        "mp4",
        "mov",
        "avi",
        "mkv",
        "webm",
    }:
        return AttachmentKind.VIDEO
    if normalized_mime.startswith("audio/") or normalized_extension in {"mp3", "wav", "ogg", "m4a"}:
        return AttachmentKind.AUDIO
    if normalized_mime == "application/pdf" or normalized_extension == "pdf":
        return AttachmentKind.PDF
    return AttachmentKind.FILE


def permalink(base_url: str, team: str, post_id: str) -> str:
    return f"{base_url.rstrip('/')}/{team}/pl/{post_id}"


def from_milliseconds(raw: object) -> datetime | None:
    if not isinstance(raw, int | float | str) or not raw:
        return None
    return datetime.fromtimestamp(int(raw) / 1000, tz=UTC)


def created_at(post: dict[str, Any]) -> datetime | None:
    return from_milliseconds(post.get("create_at"))


def post_to_submission(
    post: dict[str, Any],
    *,
    ref: ChannelRef,
    channel_title: str,
    base_url: str = "https://time.cu.ru",
    author: str | None = None,
    include_replies: bool = False,
) -> NewsSubmission | None:
    if not is_newsworthy(post, include_replies):
        return None
    body = post_body(post)
    published = created_at(post)
    extra: dict[str, Any] = {"parser": "time", "channel": ref.channel, "team": ref.team}
    if author:
        extra["author"] = author
    edited = from_milliseconds(post.get("edit_at"))
    if edited:
        extra["edited_at"] = edited.isoformat()
    return NewsSubmission(
        external_id=str(post["id"]),
        source=ref.slug,
        title=guess_title(body),
        body_md=body,
        source_link=HttpUrl(permalink(base_url, ref.team, str(post["id"]))),
        source_text=f"{channel_title}, TiMe",
        published_at=published,
        lang="ru",
        attachments=[],
        extra=extra,
    )


def parse_channels(spec: str) -> list[ChannelRef]:
    refs: list[ChannelRef] = []
    for chunk in spec.split(","):
        normalized = chunk.strip()
        if not normalized:
            continue
        try:
            refs.append(ChannelRef.parse(normalized))
        except ValueError:
            continue
    return refs
