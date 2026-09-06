import html
import time
from datetime import UTC, datetime
from html.parser import HTMLParser
from typing import Any

from thirdnews_contracts import AttachmentInput, AttachmentKind, NewsSubmission

from ...domain.entities.feed_source import FeedSource


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.hidden = 0

    def handle_starttag(self, tag: str, attrs: Any) -> None:
        del attrs
        if tag in {"script", "style", "iframe", "object"}:
            self.hidden += 1
        elif tag in {"p", "div", "br", "li", "h1", "h2", "h3", "h4"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "iframe", "object"} and self.hidden:
            self.hidden -= 1
        elif tag in {"p", "div", "li"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.hidden:
            self.parts.append(data)


def clean_markup(value: str) -> str:
    parser = TextExtractor()
    parser.feed(value)
    extracted = html.unescape("".join(parser.parts))
    lines = [" ".join(line.split()) for line in extracted.splitlines()]
    return "\n\n".join(line for line in lines if line)


def parse_feeds(spec: str) -> list[FeedSource]:
    result: list[FeedSource] = []
    for chunk in spec.split(","):
        source, separator, url = chunk.strip().partition("|")
        if separator and source and url:
            result.append(FeedSource(source.strip(), url.strip()))
    return result


def published_at(entry: Any) -> datetime | None:
    for field in ("published_parsed", "updated_parsed"):
        value = getattr(entry, field, None)
        if value:
            return datetime.fromtimestamp(time.mktime(value), tz=UTC)
    return None


def attachments(entry: Any) -> list[AttachmentInput]:
    result: list[AttachmentInput] = []
    for enclosure in getattr(entry, "enclosures", []) or []:
        url = enclosure.get("href")
        if not url:
            continue
        mime = str(enclosure.get("type") or "")
        kind = AttachmentKind.FILE
        if mime.startswith("image/"):
            kind = AttachmentKind.IMAGE
        elif mime.startswith("video/"):
            kind = AttachmentKind.VIDEO
        elif mime.startswith("audio/"):
            kind = AttachmentKind.AUDIO
        elif mime == "application/pdf":
            kind = AttachmentKind.PDF
        result.append(AttachmentInput(kind=kind, url=url, mime=mime or None))
    return result


def to_submission(
    source: str,
    entry: Any,
    *,
    max_age_days: int,
) -> NewsSubmission | None:
    published = published_at(entry)
    if published and (datetime.now(UTC) - published).days > max_age_days:
        return None
    external_id = getattr(entry, "id", None) or getattr(entry, "link", None)
    if not external_id:
        return None
    raw_body = (
        entry.content[0].value if getattr(entry, "content", None) else getattr(entry, "summary", "")
    )
    body = clean_markup(raw_body or getattr(entry, "title", ""))
    if not body:
        return None
    return NewsSubmission(
        source=source,
        external_id=str(external_id),
        title=clean_markup(getattr(entry, "title", "")) or None,
        body_md=body,
        source_link=getattr(entry, "link", None),
        published_at=published,
        attachments=attachments(entry),
        extra={"parser": "rss"},
    )
