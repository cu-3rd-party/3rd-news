from __future__ import annotations

from fastapi import APIRouter, Request, Response

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/healthz")
@router.get("/live")
async def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/startup")
async def startup(request: Request, response: Response) -> dict[str, str]:
    initialized = request.app.state.app_initialized
    response.status_code = 200 if initialized else 503
    return {"status": "started" if initialized else "starting"}


@router.get("/ready")
async def ready(request: Request, response: Response) -> dict:
    resources = request.app.state.resources
    checks = await resources.status() if resources else request.app.state.dependencies
    healthy = request.app.state.app_initialized and all(checks.values())
    response.status_code = 200 if healthy else 503
    return {"status": "ready" if healthy else "not_ready", "dependencies": checks}
