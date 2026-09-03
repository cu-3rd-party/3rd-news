"""FastAPI application for the 3rd-news main service."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import queue
from .bootstrap import bootstrap
from .config import settings
from .db import SessionLocal
from .routers import (
    admin_catalog,
    admin_news,
    admin_taxonomy,
    auth,
    callbacks,
    ingest,
    news,
)

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.media_root.mkdir(parents=True, exist_ok=True)
    async with SessionLocal() as session:
        await bootstrap(session)
    yield
    await queue.close_client()


app = FastAPI(
    title="3rd-news",
    version="0.1.0",
    summary="University news aggregation: ingest, classify, deliver",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(ingest.router)
app.include_router(news.router)
app.include_router(callbacks.router)
app.include_router(admin_taxonomy.router)
app.include_router(admin_catalog.router)
app.include_router(admin_news.router)

# Attachments are served straight off the volume; put a CDN or nginx in front
# of this path in production.
app.mount(
    settings.media_base_url,
    StaticFiles(directory=settings.media_root, check_dir=False),
    name="media",
)


@app.get("/health", tags=["meta"])
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "main"}
