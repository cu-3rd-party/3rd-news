from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any, cast

import pytest
from fastapi.responses import JSONResponse

from lib.app import create_app
from lib.core.config import Settings
from lib.handlers.router import create_router
from lib.infra.storage.memory_health import MemoryHealthStorage
from lib.interactor.use_cases.supervise import supervise_poller


def _ready_endpoint(app) -> Callable[[], Any]:
    route = next(route for route in app.routes if getattr(route, "path", None) == "/health/ready")
    return cast("Callable[[], Any]", route.endpoint)


@pytest.mark.asyncio
async def test_ready_returns_503_before_a_successful_poll_cycle() -> None:
    response = await _ready_endpoint(create_router([]))()
    assert isinstance(response, JSONResponse)
    assert response.status_code == 503


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "settings",
    [
        Settings.model_validate({"news_api_key": "", "feeds": "campus|https://feed.test"}),
        Settings.model_validate({"news_api_key": "tn2_synthetic", "feeds": ""}),
    ],
)
async def test_missing_runtime_configuration_fails_startup(settings: Settings) -> None:
    app = create_app(settings)
    with pytest.raises(RuntimeError):
        async with app.router.lifespan_context(app):
            pass


@pytest.mark.asyncio
async def test_failed_poller_is_restarted_and_readiness_stays_false() -> None:
    attempts = 0
    restarted = asyncio.Event()

    async def runner() -> None:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("synthetic poller failure")
        restarted.set()
        await asyncio.Event().wait()

    health = MemoryHealthStorage()
    task = asyncio.create_task(supervise_poller(health, runner, retry_delay_s=0))
    await asyncio.wait_for(restarted.wait(), timeout=1)
    assert attempts == 2
    assert health.ready is False
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
