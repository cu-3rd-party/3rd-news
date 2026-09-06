from typing import Any

from fastapi import APIRouter

from ..interactor.interfaces.clients.parser_application import ParserApplication
from .common import resources_from


def create_router(holder: list[ParserApplication]) -> APIRouter:
    router = APIRouter()

    @router.get("/status")
    async def status() -> dict[str, Any]:
        resources = resources_from(holder)
        details = resources.status_details()
        runs = details.pop("last_runs")
        details["last_runs"] = {key: run_output(result) for key, result in runs.items()}
        return details

    return router


def run_output(result: Any) -> dict[str, Any]:
    return {
        "created": result.created,
        "duplicates": result.duplicates,
        "skipped": result.skipped,
        "error": result.error,
        "finished_at": result.finished_at,
    }
