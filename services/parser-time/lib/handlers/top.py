from pathlib import Path

from fastapi import APIRouter

from ..interactor.interfaces.clients.parser_application import ParserApplication
from .catalog import create_router as create_catalog_router
from .health import create_router as create_health_router
from .poll import create_router as create_poll_router
from .selection import create_router as create_selection_router
from .status import create_router as create_status_router
from .ui import create_router as create_ui_router


def create_router(holder: list[ParserApplication], static_dir: Path) -> APIRouter:
    router = APIRouter()
    router.include_router(create_health_router())
    router.include_router(create_ui_router(static_dir))
    router.include_router(create_catalog_router(holder))
    router.include_router(create_selection_router(holder))
    router.include_router(create_poll_router(holder))
    router.include_router(create_status_router(holder))
    return router
