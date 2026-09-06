from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PollPolicy:
    max_age_days: int
    posts_per_page: int
    max_pages: int
    include_replies: bool
    authors: str
    download_attachments: bool
    max_attachment_bytes: int
