from typing import Any

from lib.domain import NewsState
from lib.infra.storage.postgres.models import AuditLog, News, OutboxEvent
from lib.interactor.errors import NotFoundError
from sqlalchemy import select


class NewsAdministrationBase:
    def __init__(self, max_attempts: int = 5) -> None:
        self.max_attempts = max_attempts

    async def get(self, session: Any, news_id: Any, *, lock: bool = False) -> News:
        query = select(News).where(News.id == news_id)
        if lock:
            query = query.with_for_update()
        news = (await session.execute(query)).scalar_one_or_none()
        if news is None or news.status == NewsState.DELETED:
            raise NotFoundError("news not found")
        return news

    async def add_event(
        self,
        session: Any,
        news: News,
        topic: str,
        extra: dict[str, Any] | None = None,
    ) -> None:
        session.add(
            OutboxEvent(
                topic=topic,
                aggregate_id=news.id,
                payload={
                    "news_id": str(news.id),
                    "revision": news.revision,
                    "status": str(news.status),
                    **(extra or {}),
                },
            )
        )

    def add_audit(
        self,
        session: Any,
        actor: str,
        action: Any,
        news_id: Any,
        payload: dict[str, Any] | None = None,
    ) -> None:
        session.add(
            AuditLog(
                actor=actor,
                action=str(action),
                entity_type="news",
                entity_id=str(news_id),
                payload=payload or {},
            )
        )
