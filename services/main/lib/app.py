from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from lib.core.app_init import init_app_state, init_middleware, init_router
from lib.core.config import Settings
from lib.core.logging import configure_logging
from lib.infra.resources import AppResources
from lib.infra.storage.postgres.bootstrap_storage import SqlAlchemyBootstrapStorage
from lib.interactor.use_cases.bootstrap_data import BootstrapData


def create_app(
    settings: Settings | None = None,
    *,
    database=None,
    search=None,
    storage=None,
    auth=None,
) -> FastAPI:
    settings = settings or Settings()
    configure_logging(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        resources = None
        try:
            resources = await AppResources.create(settings, **app.state.resource_overrides)
            app.state.resources = resources
            app.state.database = resources.database
            app.state.search = resources.search
            app.state.storage = resources.storage
            app.state.auth = resources.auth
            await BootstrapData(
                settings,
                resources.auth,
                SqlAlchemyBootstrapStorage(resources.database.session_factory),
            ).execute()
            app.state.dependencies = await resources.status()
            app.state.app_initialized = True
            yield
        finally:
            app.state.app_initialized = False
            if resources is not None:
                await resources.close()
            app.state.resources = None

    app = FastAPI(
        title="3rd-news",
        version="2.0.0",
        docs_url="/api/docs" if settings.environment != "production" else None,
        redoc_url=None,
        openapi_url="/api/openapi.json" if settings.environment != "production" else None,
        lifespan=lifespan,
    )
    init_app_state(
        app,
        settings,
        {"database": database, "search": search, "storage": storage, "auth": auth},
    )
    init_middleware(app, settings)
    init_router(app)
    return app
