from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse


def create_router(static_dir: Path) -> APIRouter:
    router = APIRouter()

    @router.get("/", include_in_schema=False)
    async def index() -> FileResponse:
        return FileResponse(static_dir / "index.html")

    return router
