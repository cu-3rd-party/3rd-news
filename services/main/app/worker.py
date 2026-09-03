"""Background worker: runs classification jobs and downloads attachments.

Started as its own container (`python -m app.worker`) so that a slow LLM
classifier or a large video can never block the API.
"""

from __future__ import annotations

import asyncio
import logging

from . import queue
from .config import settings
from .db import SessionLocal
from .dispatcher import RetryJob, fetch_attachment, run_classification_job

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("3rdnews.worker")


async def handle(queue_name: str, payload: dict) -> None:
    async with SessionLocal() as session:
        if queue_name == queue.QUEUE_CLASSIFY:
            await run_classification_job(session, payload["job_id"])
        elif queue_name == queue.QUEUE_MEDIA:
            await fetch_attachment(session, payload["attachment_id"])
        else:
            logger.warning("unknown queue %s", queue_name)


async def main() -> None:
    logger.info("worker started, listening on %s", [queue.QUEUE_CLASSIFY, queue.QUEUE_MEDIA])
    async for queue_name, payload in queue.consume(
        [queue.QUEUE_CLASSIFY, queue.QUEUE_MEDIA]
    ):
        try:
            await handle(queue_name, payload)
        except RetryJob:
            # The job row already carries the attempt count; back on the queue.
            await queue.enqueue(queue_name, payload)
        except Exception:  # noqa: BLE001 - one bad job must not kill the loop
            logger.exception("job failed on %s: %s", queue_name, payload)
            if not await queue.requeue(queue_name, payload, settings.classification_max_attempts):
                logger.error("giving up on %s: %s", queue_name, payload)


if __name__ == "__main__":
    asyncio.run(main())
