import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import cast

from fastapi import FastAPI

from lib.core.app_init import init_app_state, init_middleware, init_router
from lib.core.config import Settings, get_settings
from lib.core.logging import configure_logging
from lib.infra.resources import AppResources

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    settings = cast("Settings", app.state.settings)

    configure_logging(settings)
    resources = await AppResources.create(settings)
    app.state.resources = resources
    app.state.dependencies = await resources.status()

    app.state.app_initialized = True
    logger.info("Application initialized")

    try:
        yield
    finally:
        app.state.app_initialized = False
        await resources.close()
        app.state.resources = None
        logger.info("Application stopped")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    configure_logging(settings)

    app = FastAPI(
        title=settings.project_name,
        debug=settings.debug,
        docs_url=f"{settings.backend_api_prefix}/docs" if settings.debug else None,
        redoc_url=None,
        openapi_url=f"{settings.backend_api_prefix}/openapi.json" if settings.debug else None,
        lifespan=lifespan,
    )

    init_app_state(app, settings)
    init_middleware(app)
    init_router(app, settings)

    return app


app = create_app()
