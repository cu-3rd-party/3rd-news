import asyncio
import logging
from collections.abc import Awaitable, Callable

from ..interfaces.storage.health import HealthStorage

logger = logging.getLogger("thirdnews.parser.rss.lifecycle")


async def supervise_poller(
    health: HealthStorage,
    runner: Callable[[], Awaitable[None]],
    retry_delay_s: float,
) -> None:
    while True:
        health.record_cycle(False)
        try:
            await runner()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("RSS poller exited; retrying after bounded backoff")
        health.record_cycle(False)
        await asyncio.sleep(retry_delay_s)
