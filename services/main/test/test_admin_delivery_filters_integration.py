from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from lib.infra.storage.postgres.models import (
    Facet,
    News,
    NewsSourceLink,
    NewsVersion,
    Source,
    Submission,
)
from lib.infra.storage.postgres.repositories import (
    SqlAlchemyNewsAdminRepository,
    SqlAlchemyNewsDeliveryRepository,
)

pytestmark = pytest.mark.integration


async def sourced_news(
    session,
    source: Source,
    *,
    marker: str,
    published_at: datetime,
    gold: bool = False,
) -> News:
    news = News(status="published", published_at=published_at, is_gold=gold)
    version = NewsVersion(news=news, number=1, body_md=marker, created_by="qa")
    submission = Submission(
        source_id=source.id,
        external_id=f"{marker}-{uuid.uuid4()}",
        payload_hash=hashlib.sha256(marker.encode()).hexdigest(),
        raw_payload={"body_md": marker},
    )
    session.add_all([news, version, submission])
    await session.flush()
    news.current_version_id = version.id
    submission.news_id = news.id
    session.add(NewsSourceLink(news_id=news.id, submission_id=submission.id))
    return news


async def test_review_filters_apply_gold_source_and_missing_facet(
    integration_database,
) -> None:
    nonce = uuid.uuid4().hex
    async with integration_database() as session, session.begin():
        source = Source(slug=f"review-source-{nonce}", title="Review source")
        facet = Facet(slug=f"review-facet-{nonce}", title="Review facet")
        session.add_all([source, facet])
        await session.flush()
        expected = await sourced_news(
            session,
            source,
            marker=f"expected-{nonce}",
            published_at=datetime.now(UTC),
            gold=True,
        )
        await sourced_news(
            session,
            source,
            marker=f"ordinary-{nonce}",
            published_at=datetime.now(UTC),
            gold=False,
        )
        expected_id = expected.id

    async with integration_database() as session:
        items, total = await SqlAlchemyNewsAdminRepository(session).list_news(
            statuses=["published"],
            query_text=None,
            gold=True,
            source=f"review-source-{nonce}",
            unlabelled_facet=f"review-facet-{nonce}",
            limit=10,
            offset=0,
        )
        assert total == 1
        assert [item["id"] for item in items] == [str(expected_id)]


async def test_rss_policy_is_applied_before_order_and_limit(integration_database) -> None:
    nonce = uuid.uuid4().hex
    now = datetime.now(UTC)
    async with integration_database() as session, session.begin():
        denied = Source(slug=f"denied-{nonce}", title="Denied")
        allowed = Source(slug=f"allowed-{nonce}", title="Allowed")
        session.add_all([denied, allowed])
        await session.flush()
        await sourced_news(
            session,
            denied,
            marker=f"new-denied-{nonce}",
            published_at=now,
        )
        expected = await sourced_news(
            session,
            allowed,
            marker=f"older-allowed-{nonce}",
            published_at=now - timedelta(days=1),
        )
        expected_id = expected.id

    async with integration_database() as session:
        rows = await SqlAlchemyNewsDeliveryRepository(session).recent_published(
            1,
            editor=False,
            preset={"sources": [f"allowed-{nonce}"]},
        )
        assert [item.id for item in rows] == [expected_id]
