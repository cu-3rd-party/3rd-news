from __future__ import annotations

from typing import Any

from lib.infra.storage.postgres.models import (
    Attachment,
    Facet,
    FacetValue,
    News,
    NewsEffectiveLabel,
    NewsSourceLink,
    NewsVersion,
    Source,
    Submission,
)
from lib.interactor.interfaces.storage.news_read import NewsReadStorage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class NewsReadRepository(NewsReadStorage):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def serialize(self, news: News, *, admin: bool = False) -> dict[str, Any]:
        version = await self.session.get(NewsVersion, news.current_version_id)
        if version is None:
            raise RuntimeError(f"news {news.id} has no current version")
        labels = (
            await self.session.execute(
                select(
                    NewsEffectiveLabel,
                    Facet.slug,
                    Facet.title,
                    FacetValue.slug,
                    FacetValue.title,
                )
                .join(Facet, Facet.id == NewsEffectiveLabel.facet_id)
                .join(FacetValue, FacetValue.id == NewsEffectiveLabel.value_id)
                .where(
                    NewsEffectiveLabel.news_id == news.id,
                    Facet.enabled.is_(True),
                    FacetValue.enabled.is_(True),
                )
            )
        ).all()
        attachments = (
            (
                await self.session.execute(
                    select(Attachment)
                    .where(
                        Attachment.news_id == news.id,
                        Attachment.active.is_(True),
                        Attachment.status == "stored",
                        Attachment.object_key.is_not(None),
                    )
                    .order_by(Attachment.position)
                )
            )
            .scalars()
            .all()
        )
        sources = (
            (
                await self.session.execute(
                    select(Source.slug)
                    .join(Submission, Submission.source_id == Source.id)
                    .join(NewsSourceLink, NewsSourceLink.submission_id == Submission.id)
                    .where(NewsSourceLink.news_id == news.id)
                    .order_by(Source.slug)
                )
            )
            .scalars()
            .all()
        )
        result = {
            "id": str(news.id),
            "version_id": str(version.id),
            "number": version.number,
            "title": version.title,
            "body_md": version.body_md,
            "source_link": version.source_link,
            "source_text": version.source_text,
            "language": version.language,
            "lang": version.language,
            "published_at": news.published_at or version.source_published_at,
            "extra": version.extra,
            "status": news.status,
            "received_at": news.created_at,
            "revision": news.revision,
            "source": sources[0] if sources else None,
            "source_key": sources[0] if sources else None,
            "sources": list(dict.fromkeys(sources)),
            "urgency": news.urgency,
            "impact": news.impact,
            "editorial_priority": news.editorial_priority,
            "importance": news.importance,
            "labels": [
                {
                    "facet": facet_slug,
                    "facet_title": facet_title,
                    "value": value_slug,
                    "value_title": value_title,
                    "origin": label.origin,
                    "confidence": label.confidence,
                }
                for label, facet_slug, facet_title, value_slug, value_title in labels
            ],
            "attachments": [
                {
                    "id": str(item.id),
                    "kind": item.kind,
                    "url": f"/api/v1/media/{item.id}",
                    "filename": item.filename,
                    "mime": item.content_type,
                    "size": item.size,
                    "status": item.status,
                    "caption": item.caption,
                    "position": item.position,
                }
                for item in attachments
            ],
        }
        if admin:
            result["manual_facets"] = news.manual_facets
            result["is_gold"] = news.is_gold
        return result
