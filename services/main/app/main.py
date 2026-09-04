"""FastAPI application for the 3rd-news main service."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from . import queue
from .bootstrap import bootstrap
from .config import settings
from .db import SessionLocal
from .deps import ReadPrincipal
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

@app.get(settings.media_base_url + "/{path:path}", include_in_schema=False)
async def media(path: str, principal: ReadPrincipal) -> FileResponse:
    """Вложения — за той же авторизацией, что и сама лента.

    Раздавать их статикой было бы дырой: имена файлов попадают в выдачу, и
    любой, кому досталась ссылка, читал бы приложения к закрытым новостям без
    ключа. `<img>` заголовков не шлёт, поэтому ключ принимается и параметром
    `?api_key=` — это уже умеет ApiKeyBackend.
    """

    del principal
    root = settings.media_root.resolve()
    target = (root / path).resolve()
    # Защита от `../`: файл обязан лежать внутри корня медиа.
    if not target.is_relative_to(root) or not target.is_file():
        raise HTTPException(status_code=404, detail="файл не найден")
    return FileResponse(target)


@app.get("/preview", include_in_schema=False)
async def preview() -> FileResponse:
    """Страница, показывающая ленту глазами клиента.

    Инструмент для настройки: фильтры она строит из текущей таксономии, а
    ходит в тот же `/api/v1/news`, что и любой внешний клиент.
    """

    return FileResponse(Path(__file__).parent / "static" / "preview.html")


@app.get("/health", tags=["meta"])
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "main"}
