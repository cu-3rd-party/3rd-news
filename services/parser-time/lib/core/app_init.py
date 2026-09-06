from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from ..handlers.top import create_router
from ..infra.resources import AppResources
from .config import Settings
from .middleware import (
    ErrorHandlingMiddleware,
    ManagementAuthMiddleware,
    RequestIDMiddleware,
    SecurityHeadersMiddleware,
)


def init_app_state(app: FastAPI, settings: Settings) -> None:
    app.state.app_initialized = False
    app.state.resources = None
    app.state.settings = settings


def init_middleware(app: FastAPI, settings: Settings) -> None:
    app.add_middleware(ErrorHandlingMiddleware)
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(ManagementAuthMiddleware, settings=settings)


def init_router(
    app: FastAPI,
    resources_holder: list[AppResources],
    static_dir: Path,
) -> None:
    app.include_router(create_router(resources_holder, static_dir))
    app.mount("/static", StaticFiles(directory=static_dir), name="static")
