import logging
from collections.abc import Callable

import feedparser
from thirdnews_contracts import IngestError, IngestStatus

from ...domain.entities.feed_source import FeedSource
from ..interfaces.clients.feed import FeedClient
from ..interfaces.clients.ingest import IngestGateway
from .parse_feed import to_submission

logger = logging.getLogger("thirdnews.parser.rss")


async def poll_once(
    feed_client: FeedClient,
    ingest_client: IngestGateway,
    feeds: list[FeedSource],
    max_age_days: int,
) -> bool:
    succeeded = True
    for feed in feeds:
        try:
            parsed = feedparser.parse(await feed_client.fetch(feed.url))
        except Exception:
            logger.warning("failed to fetch configured feed %s", feed.source)
            succeeded = False
            continue
        if getattr(parsed, "bozo", False) and not parsed.entries:
            logger.warning("configured feed %s returned no valid RSS/Atom entries", feed.source)
            succeeded = False
            continue
        accepted = 0
        duplicates = 0
        skipped = 0
        for entry in parsed.entries:
            submission = to_submission(feed.source, entry, max_age_days=max_age_days)
            if submission is None:
                skipped += 1
                continue
            try:
                result = await ingest_client.submit(submission)
            except IngestError as exc:
                logger.warning(
                    "failed to submit an item from %s: HTTP %d", feed.source, exc.status_code
                )
                succeeded = False
                continue
            if result.status is IngestStatus.ACCEPTED:
                accepted += 1
            else:
                duplicates += 1
        logger.info(
            "%s: %d accepted, %d known, %d skipped",
            feed.source,
            accepted,
            duplicates,
            skipped,
        )
    return succeeded


async def run_poller(
    feed_client: FeedClient,
    ingest_client: IngestGateway,
    feeds: list[FeedSource],
    max_age_days: int,
    poll_interval_s: float,
    on_cycle: Callable[[bool], None],
) -> None:
    import asyncio

    while True:
        succeeded = await poll_once(feed_client, ingest_client, feeds, max_age_days)
        on_cycle(succeeded)
        await asyncio.sleep(poll_interval_s)
