from typing import Any, cast

from fastapi import APIRouter, FastAPI, Request, Response, status

from lib.dto.health import HealthResponse, LivenessResponse

router = APIRouter(prefix="/health", tags=["health"])

NOT_READY_RESPONSES: dict[int | str, dict[str, Any]] = {
    status.HTTP_503_SERVICE_UNAVAILABLE: {"model": HealthResponse},
}


def _app(request: Request) -> FastAPI:
    return cast("FastAPI", request.app)


def _dependencies(request: Request) -> dict[str, bool]:
    return cast("dict[str, bool]", _app(request).state.dependencies)


@router.get("/healthz")
async def healthz() -> LivenessResponse:
    return LivenessResponse()


@router.get("/startup", responses=NOT_READY_RESPONSES)
async def startup(request: Request, response: Response) -> HealthResponse:
    app = _app(request)
    dependencies = _dependencies(request)
    is_initialized = cast("bool", app.state.app_initialized)
    is_ready = is_initialized and all(dependencies.values())

    if not is_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return HealthResponse(
        status="ok" if is_ready else "not_ready",
        dependencies=dependencies,
    )


@router.get("/ready", responses=NOT_READY_RESPONSES)
async def ready(request: Request, response: Response) -> HealthResponse:
    dependencies = _dependencies(request)
    is_ready = all(dependencies.values())

    if not is_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return HealthResponse(
        status="ready" if is_ready else "not_ready",
        dependencies=dependencies,
    )
