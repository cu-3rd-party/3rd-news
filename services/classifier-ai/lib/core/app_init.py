from fastapi import FastAPI
from thirdnews_contracts import CallbackClient, MemoryReplayStorage

from ..handlers.top import create_router
from ..infra.resources import AppResources
from .config import Settings
from .middleware import ErrorHandlingMiddleware, RequestIDMiddleware


def init_app_state(app: FastAPI, settings: Settings, resources: AppResources) -> None:
    app.state.app_initialized = False
    app.state.resources = resources
    app.state.settings = settings


def init_middleware(app: FastAPI) -> None:
    app.add_middleware(ErrorHandlingMiddleware)
    app.add_middleware(RequestIDMiddleware)


def init_router(app: FastAPI, settings: Settings, resources: AppResources) -> None:
    callback_client = (
        CallbackClient(
            settings.classifier_private_key,
            settings.classifier_issuer or settings.classifier_node_id,
            settings.classifier_node_id,
        )
        if settings.classifier_private_key is not None
        and (settings.classifier_issuer or settings.classifier_node_id)
        else None
    )
    app.include_router(
        create_router(
            settings,
            resources.classifier,
            resources.background,
            callback_client,
            MemoryReplayStorage(),
        )
    )
