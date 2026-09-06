import asyncio

import aiohttp

from lib.core.config import Settings


async def check(settings: Settings) -> bool:
    timeout = aiohttp.ClientTimeout(total=settings.healthcheck_timeout_seconds)
    url = f"http://{settings.api_healthcheck_host}:{settings.api_port}/health/ready"
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url, allow_redirects=False) as response:
            return response.status == 200


def main() -> None:
    if not asyncio.run(check(Settings())):
        raise SystemExit(1)
