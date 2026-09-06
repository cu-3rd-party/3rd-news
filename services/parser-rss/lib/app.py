from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .core.app_init import init_app_state, init_middleware, init_router
from .core.config import Settings, get_settings
from .core.logging import configure_logging
from .infra.resources import AppResources


def create_app(settings_override: Settings | None = None) -> FastAPI:
    settings = settings_override or get_settings()
    resources_holder: list[AppResources] = []

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        resources = await AppResources.create(settings)
        resources_holder.append(resources)
        app.state.resources = resources
        app.state.app_initialized = True
        try:
            yield
        finally:
            app.state.app_initialized = False
            await resources.close()
            app.state.resources = None

    configure_logging(settings)
    app = FastAPI(
        title=settings.project_name,
        version="2.0.0",
        debug=settings.debug,
        docs_url="/docs" if settings.debug else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.debug else None,
        lifespan=lifespan,
    )
    init_app_state(app, settings)
    init_middleware(app)
    init_router(app, resources_holder)
    return app


app = create_app()
