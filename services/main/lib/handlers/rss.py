from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response

from lib.core.service_factory import service_factory

from .access_policy import enforce_news_access, enforce_visibility_barrier
from .common import news_dict
from .dependencies import DbSession, ReadPrincipal

router = APIRouter()


@router.get("/api/v1/rss.xml")
async def rss(request: Request, session: DbSession, principal: ReadPrincipal) -> Response:
    await enforce_visibility_barrier(session, principal)
    rows = await service_factory.news_delivery(session).recent_published(
        100,
        editor=principal.allows("editor"),
        preset=principal.filter_preset or {},
    )
    items = []
    for news in rows:
        try:
            await enforce_news_access(session, news, principal)
        except HTTPException as error:
            if error.status_code == 404:
                continue
            raise
        value = await news_dict(session, news)
        title = value["title"] or "University news"
        link = f"{request.app.state.settings.public_base_url}/api/v1/news/{news.id}"
        items.append(
            f"<item><guid>{news.id}</guid><title>{xml_escape(title)}</title><link>{xml_escape(link)}</link><description>{xml_escape(value['body_md'])}</description></item>"
        )
    return Response(
        f'<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>3rd-news</title>{"".join(items)}</channel></rss>',
        media_type="application/rss+xml",
    )


def xml_escape(value: str) -> str:
    return (
        value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    )
