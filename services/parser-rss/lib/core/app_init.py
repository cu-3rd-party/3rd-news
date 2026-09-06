from fastapi import FastAPI

from ..handlers.top import create_router
from ..infra.resources import AppResources
from .config import Settings
from .middleware import ErrorHandlingMiddleware, RequestIDMiddleware


def init_app_state(app: FastAPI, settings: Settings) -> None:
    app.state.app_initialized = False
    app.state.resources = None
    app.state.settings = settings


def init_middleware(app: FastAPI) -> None:
    app.add_middleware(ErrorHandlingMiddleware)
    app.add_middleware(RequestIDMiddleware)


def init_router(app: FastAPI, resources_holder: list[AppResources]) -> None:
    def is_ready() -> bool:
        if not resources_holder:
            return False
        resources = resources_holder[0]
        poller = resources.poller
        return poller is not None and not poller.done() and resources.health.ready

    app.include_router(create_router(is_ready))
