from __future__ import annotations

from typing import Any

from lib.domain import NewsState
from lib.infra.storage.postgres.models import Attachment, News, NewsSourceLink, Submission
from lib.interactor.errors import ValidationError
from lib.interactor.interfaces.storage.news_merge import NewsMergeStorage
from sqlalchemy import select, update

from .base import NewsAdministrationBase
from .provenance import NewsProvenance


class SqlAlchemyNewsMergeStorage(NewsAdministrationBase, NewsMergeStorage):
    async def merge(self, session: Any, target: News, source_ids: list[Any], actor: str) -> None:
        provenance = NewsProvenance()
        for source_id in source_ids:
            source = await self.get(session, source_id, lock=True)
            if source.id == target.id:
                raise ValidationError("a news item cannot be merged into itself")
            submissions = (
                (
                    await session.execute(
                        select(NewsSourceLink).where(NewsSourceLink.news_id == source.id)
                    )
                )
                .scalars()
                .all()
            )
            for link in submissions:
                link.news_id = target.id
                link.relation = "merged"
                submission = await session.get(Submission, link.submission_id)
                if submission is not None:
                    submission.news_id = target.id
            submission_ids = [link.submission_id for link in submissions]
            await session.execute(
                update(Attachment)
                .where(Attachment.submission_id.in_(submission_ids))
                .values(news_id=target.id)
            )
            await provenance.copy(session, source, target, "merge")
            source.status = NewsState.ARCHIVED
            source.revision += 1
            source.visibility_revision += 1
            await self.add_event(session, source, "search.projection.requested.v2")
        target.status = NewsState.NEEDS_REVIEW
        target.revision += 1
        target.visibility_revision += 1
        await self.add_event(session, target, "search.projection.requested.v2")
        self.add_audit(
            session, actor, "merge", target.id, {"sources": [str(item) for item in source_ids]}
        )
