from __future__ import annotations

from datetime import datetime
from typing import Any

from lib.domain import NewsState
from lib.infra.storage.postgres.models import (
    Attachment,
    News,
    NewsSourceLink,
    NewsVersion,
    Submission,
)
from lib.interactor.errors import ValidationError
from lib.interactor.interfaces.storage.news_split import NewsSplitStorage
from sqlalchemy import select, update

from .base import NewsAdministrationBase
from .provenance import NewsProvenance


class SqlAlchemyNewsSplitStorage(NewsAdministrationBase, NewsSplitStorage):
    async def split(self, session: Any, news: News, submission_ids: list[Any], actor: str) -> News:
        links = (
            await session.execute(
                select(NewsSourceLink, Submission)
                .join(Submission)
                .where(
                    NewsSourceLink.news_id == news.id,
                    NewsSourceLink.submission_id.in_(submission_ids),
                )
            )
        ).all()
        all_links = (
            await session.execute(select(NewsSourceLink).where(NewsSourceLink.news_id == news.id))
        ).all()
        if not links or len(links) == len(all_links):
            raise ValidationError("split must move some, but not all, source submissions")
        created = News(status=NewsState.NEEDS_REVIEW)
        session.add(created)
        await session.flush()
        first = links[0][1].raw_payload
        source_published_at = first.get("published_at")
        if isinstance(source_published_at, str):
            try:
                source_published_at = datetime.fromisoformat(
                    source_published_at.replace("Z", "+00:00")
                )
            except ValueError as error:
                raise ValidationError(
                    "source submission contains an invalid publication time"
                ) from error
        version = NewsVersion(
            news_id=created.id,
            number=1,
            title=first.get("title"),
            body_md=first.get("body_md", ""),
            source_link=first.get("source_link"),
            source_text=first.get("source_text"),
            language=first.get("language") or first.get("lang"),
            source_published_at=source_published_at,
            extra=first.get("extra", {}),
            created_by=actor,
        )
        session.add(version)
        await session.flush()
        created.current_version_id = version.id
        for link, submission in links:
            link.news_id = created.id
            link.relation = "split"
            submission.news_id = created.id
        moved_submission_ids = [submission.id for _, submission in links]
        await session.execute(
            update(Attachment)
            .where(Attachment.submission_id.in_(moved_submission_ids))
            .values(news_id=created.id)
        )
        await NewsProvenance().copy(session, news, created, "split")
        news.status = NewsState.NEEDS_REVIEW
        news.revision += 1
        news.visibility_revision += 1
        await self.add_event(session, news, "search.projection.requested.v2")
        await self.add_event(session, created, "search.projection.requested.v2")
        self.add_audit(session, actor, "split", news.id, {"created": str(created.id)})
        return created
