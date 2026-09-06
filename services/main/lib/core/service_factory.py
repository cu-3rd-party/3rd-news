from __future__ import annotations

from typing import Any

from lib.infra.clients.http import SafeFetcher, UrlPolicy
from lib.infra.clients.nats import StreamSettings
from lib.infra.clients.nats.dead_letters import DeadLetters
from lib.infra.storage.postgres.labels import SqlAlchemyLabelStorage
from lib.infra.storage.postgres.news_administration import (
    SqlAlchemyNewsLifecycleStorage,
    SqlAlchemyNewsMergeStorage,
    SqlAlchemyNewsSplitStorage,
)
from lib.infra.storage.postgres.pipeline import SqlAlchemyPipelineStorage
from lib.infra.storage.postgres.repositories import (
    AuthAccountRepository,
    DeliveryRepository,
    NewsReadRepository,
    PersistenceRepository,
    SqlAlchemyIngestRepository,
    SqlAlchemyNewsAdminRepository,
    SqlAlchemyNewsDeliveryRepository,
    SqlAlchemyTaxonomyRepository,
)
from lib.infra.storage.postgres.repositories.api_key_repository import ApiKeyRepository
from lib.infra.storage.postgres.repositories.classifier_repository import ClassifierRepository
from lib.infra.storage.postgres.repositories.context_repository import ContextRepository
from lib.infra.storage.postgres.repositories.editorial_rule_repository import (
    EditorialRuleRepository,
)
from lib.infra.storage.postgres.repositories.raw_audit_repository import RawAuditRepository
from lib.infra.storage.postgres.repositories.source_repository import SourceRepository
from lib.infra.storage.postgres.submissions import (
    SqlAlchemySubmissionIdentityStorage,
    SqlAlchemySubmissionWriterStorage,
)
from lib.infra.storage.postgres.unit_of_work import SqlAlchemyUnitOfWork


class ServiceFactory:
    def source(self, session: Any) -> SourceRepository:
        return SourceRepository(session)

    def api_key(self, session: Any) -> ApiKeyRepository:
        return ApiKeyRepository(session)

    def classifier(self, session: Any) -> ClassifierRepository:
        return ClassifierRepository(session)

    def context(self, session: Any) -> ContextRepository:
        return ContextRepository(session)

    def editorial_rule(self, session: Any) -> EditorialRuleRepository:
        return EditorialRuleRepository(session)

    def news_admin(self, session: Any) -> SqlAlchemyNewsAdminRepository:
        return SqlAlchemyNewsAdminRepository(session)

    def news_delivery(self, session: Any) -> SqlAlchemyNewsDeliveryRepository:
        return SqlAlchemyNewsDeliveryRepository(session)

    def taxonomy(self, session: Any) -> SqlAlchemyTaxonomyRepository:
        return SqlAlchemyTaxonomyRepository(session)

    def auth_account(self, session: Any) -> AuthAccountRepository:
        return AuthAccountRepository(session)

    def delivery(self, session: Any) -> DeliveryRepository:
        return DeliveryRepository(session)

    def ingest(self, session: Any) -> SqlAlchemyIngestRepository:
        return SqlAlchemyIngestRepository(session)

    def raw_audit(self, session: Any) -> RawAuditRepository:
        return RawAuditRepository(session)

    def news_reader(self, session: Any) -> NewsReadRepository:
        return NewsReadRepository(session)

    def persistence(self, session: Any) -> PersistenceRepository:
        return PersistenceRepository(session)

    def unit_of_work(self, session_factory: Any) -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(session_factory)

    def labels(self) -> SqlAlchemyLabelStorage:
        return SqlAlchemyLabelStorage()

    def submission_identity(self) -> SqlAlchemySubmissionIdentityStorage:
        return SqlAlchemySubmissionIdentityStorage()

    def submission_writer(self) -> SqlAlchemySubmissionWriterStorage:
        return SqlAlchemySubmissionWriterStorage()

    def news_lifecycle(self, max_attempts: int = 5) -> SqlAlchemyNewsLifecycleStorage:
        return SqlAlchemyNewsLifecycleStorage(max_attempts)

    def news_merge(self) -> SqlAlchemyNewsMergeStorage:
        return SqlAlchemyNewsMergeStorage()

    def news_split(self) -> SqlAlchemyNewsSplitStorage:
        return SqlAlchemyNewsSplitStorage()

    def pipeline(self) -> SqlAlchemyPipelineStorage:
        return SqlAlchemyPipelineStorage()

    def fetcher(self, settings: Any, hosts: list[str]) -> SafeFetcher:
        return SafeFetcher(
            policy=UrlPolicy.with_service_hosts(
                hosts, max_redirects=settings.fetch_max_redirects
            ),
            timeout_seconds=settings.fetch_timeout_seconds,
            max_bytes=settings.fetch_max_bytes,
        )

    def dead_letters(self, settings: Any) -> DeadLetters:
        return DeadLetters(settings)

    def duplicate_window_seconds(self) -> int:
        return StreamSettings().duplicate_window_seconds


service_factory = ServiceFactory()
