from fastapi import FastAPI

from lib.core.config import Settings
from lib.core.middleware.error_middleware import ErrorHandlingMiddleware
from lib.core.middleware.request_id_middleware import RequestIDMiddleware
from lib.handlers.top import api_router
from lib.infra.resources import AppResources


def init_app_state(app: FastAPI, settings: Settings) -> None:
    app.state.app_initialized = False
    app.state.dependencies = AppResources.initial_status()
    app.state.resources = None
    app.state.settings = settings


def init_middleware(app: FastAPI) -> None:
    app.add_middleware(ErrorHandlingMiddleware)
    app.add_middleware(RequestIDMiddleware)


def init_router(app: FastAPI, settings: Settings) -> None:
    app.include_router(api_router, prefix=settings.backend_api_prefix)
