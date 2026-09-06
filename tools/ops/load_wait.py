import asyncio
import time

import aiohttp

from tools.ops.load_http import json_request
from tools.ops.load_settings import LoadSettings

TERMINAL_NEWS_STATUSES = frozenset({"published", "needs_review", "rejected", "deleted"})


async def wait_for_news_id(
    session: aiohttp.ClientSession,
    settings: LoadSettings,
    headers: dict[str, str],
    submission_id: str,
    deadline: float,
) -> str:
    while time.monotonic() < deadline:
        _, payload = await json_request(
            session,
            "GET",
            f"{settings.base_url}/api/v1/submissions/{submission_id}",
            expected={200},
            headers=headers,
        )
        news_id = payload.get("news_id")
        if isinstance(news_id, str) and news_id:
            return news_id
        await asyncio.sleep(settings.poll_seconds)
    raise TimeoutError(f"submission {submission_id} did not acquire news_id")


async def wait_for_terminal_news(
    session: aiohttp.ClientSession,
    settings: LoadSettings,
    headers: dict[str, str],
    news_id: str,
    deadline: float,
) -> str:
    while time.monotonic() < deadline:
        status, payload = await json_request(
            session,
            "GET",
            f"{settings.base_url}/api/v1/admin/news/{news_id}",
            expected={200, 404},
            headers=headers,
        )
        if status == 200:
            news_status = payload.get("status")
            if isinstance(news_status, str) and news_status in TERMINAL_NEWS_STATUSES:
                return news_status
        await asyncio.sleep(settings.poll_seconds)
    raise TimeoutError(f"news {news_id} did not reach a terminal state")
