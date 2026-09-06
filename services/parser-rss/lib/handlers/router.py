from collections.abc import Callable

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ..dto.health_response import HealthResponse


def create_router(is_ready: Callable[[], bool]) -> APIRouter:
    router = APIRouter()

    @router.get("/health/healthz", response_model=HealthResponse)
    async def healthz() -> HealthResponse:
        return HealthResponse(status="ok")

    @router.get("/health/ready")
    @router.get("/health/startup")
    async def ready() -> JSONResponse:
        if not is_ready():
            return JSONResponse(
                HealthResponse(status="not-ready").model_dump(),
                status_code=503,
            )
        return JSONResponse(HealthResponse(status="ready").model_dump())

    return router
