from typing import Any

from fastapi import APIRouter

from ..infra.resources import AppResources
from .common import resources_from


def create_router(holder: list[AppResources]) -> APIRouter:
    router = APIRouter()

    @router.get("/status")
    async def status() -> dict[str, Any]:
        resources = resources_from(holder)
        settings = resources.settings
        runs = resources.storage.runs()
        return {
            "time_base_url": settings.time_base_url,
            "authorized": bool(
                settings.time_cookie.get_secret_value() or settings.time_token.get_secret_value()
            ),
            "news_url": settings.news_url,
            "news_key_configured": bool(settings.news_api_key.get_secret_value()),
            "poll_interval_s": settings.poll_interval_s,
            "selected": len(resources.storage.selected()),
            "last_runs": {key: run_output(result) for key, result in runs.items()},
        }

    return router


def run_output(result: Any) -> dict[str, Any]:
    return {
        "created": result.created,
        "duplicates": result.duplicates,
        "skipped": result.skipped,
        "error": result.error,
        "finished_at": result.finished_at,
    }
