"""Skeleton for a new parser. Copy this directory and fill in `fetch_items`.

A parser is not a plugin of the main service — it is an independent program,
in this repository or in yours, in Python or in anything else. Its whole
contract is: get an ingest API key from the admin, then POST news items to
`/api/v1/ingest/news`. See `docs/guides/writing-a-parser.md`.

Run it:

    NEWS_URL=http://localhost:8000 NEWS_API_KEY=tnk_... SOURCE_KEY=my-channel \\
        python -m app.main
"""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Iterator
from datetime import datetime, timezone

from thirdnews_contracts import (
    AttachmentInput,
    AttachmentKind,
    IngestClient,
    IngestError,
    NewsSubmission,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("3rdnews.parser.template")

NEWS_URL = os.getenv("NEWS_URL", "http://main:8000")
API_KEY = os.getenv("NEWS_API_KEY", "")
#: Slug of the source in the admin. Created automatically on first submission.
SOURCE_KEY = os.getenv("SOURCE_KEY", "my-channel")
INTERVAL_S = int(os.getenv("POLL_INTERVAL_S", "600"))


def fetch_items() -> Iterator[NewsSubmission]:
    """Yield everything the channel currently shows.

    There is no need to remember what was already sent: the main service keys
    on `(source_key, external_id)` and answers `duplicate` for repeats. Just
    make sure `external_id` is stable — a message id, a permalink, a guid.
    """

    yield NewsSubmission(
        external_id="example-1",
        source_key=SOURCE_KEY,
        title="Пример новости",
        body_md=(
            "Основной текст в **Markdown**.\n\n"
            "Может быть сколь угодно длинным — сервис его не режет."
        ),
        # Either a link to the original post...
        source_link="https://example.edu/posts/1",
        # ...or, when there is none, the human name of the channel.
        source_text="Пример канала",
        published_at=datetime.now(timezone.utc),
        attachments=[
            AttachmentInput(
                kind=AttachmentKind.IMAGE,
                url="https://example.edu/posts/1/cover.jpg",
                caption="Афиша",
            )
        ],
        # Labels you already know for sure. Everything else is left to the
        # classifiers and to the editors.
        labels={},
        extra={"parser": "template"},
    )


def poll_once(client: IngestClient) -> None:
    created = duplicates = 0
    for submission in fetch_items():
        try:
            result = client.submit(submission)
        except IngestError:
            logger.exception("failed to submit %s", submission.external_id)
            continue
        if result.status.value == "created":
            created += 1
        else:
            duplicates += 1
    logger.info("%s: %d new, %d already known", SOURCE_KEY, created, duplicates)


def main() -> None:
    if not API_KEY:
        raise SystemExit("NEWS_API_KEY is required (create an ingest key in the admin)")
    client = IngestClient(NEWS_URL, API_KEY)
    while True:
        poll_once(client)
        time.sleep(INTERVAL_S)


if __name__ == "__main__":
    main()
