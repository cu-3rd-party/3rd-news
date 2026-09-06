from fastapi import APIRouter

from ..dto.health_response import HealthResponse


def create_router() -> APIRouter:
    router = APIRouter(tags=["meta"])

    @router.get("/health", response_model=HealthResponse)
    @router.get("/health/healthz", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse(status="ok")

    return router
