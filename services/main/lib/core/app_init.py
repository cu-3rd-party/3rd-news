from __future__ import annotations

from fastapi import FastAPI

from lib.core.config import Settings
from lib.core.middleware import ErrorHandlingMiddleware, RequestIDMiddleware, RequestSizeMiddleware
from lib.handlers.top import router as api_router
from lib.infra.resources import AppResources


def init_app_state(app: FastAPI, settings: Settings, overrides: dict) -> None:
    app.state.settings = settings
    app.state.resource_overrides = overrides
    app.state.resources = None
    app.state.database = overrides.get("database")
    app.state.search = overrides.get("search")
    app.state.storage = overrides.get("storage")
    app.state.auth = overrides.get("auth")
    app.state.dependencies = AppResources.initial_status()
    app.state.app_initialized = False


def init_middleware(app: FastAPI, settings: Settings) -> None:
    app.add_middleware(ErrorHandlingMiddleware)
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(RequestSizeMiddleware, max_bytes=settings.request_max_bytes)


def init_router(app: FastAPI) -> None:
    app.include_router(api_router)
