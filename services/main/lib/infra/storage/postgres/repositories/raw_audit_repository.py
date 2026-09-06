from datetime import UTC, datetime, timedelta
from uuid import UUID

from lib.infra.storage.postgres.models import AuditLog, ProcessingAttempt
from lib.interactor.errors import NotFoundError
from lib.interactor.interfaces.storage.raw_audit import RawAuditStorage
from sqlalchemy.ext.asyncio import AsyncSession


class RawAuditRepository(RawAuditStorage):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def read(
        self, attempt_id: UUID, *, actor: str, retention_days: int
    ) -> tuple[bytes | None, bytes | None]:
        attempt = await self.session.get(ProcessingAttempt, attempt_id)
        if attempt is None or attempt.started_at <= datetime.now(UTC) - timedelta(
            days=retention_days
        ):
            raise NotFoundError("raw audit is unavailable or expired")
        self.session.add(
            AuditLog(
                actor=actor,
                action="raw_audit.read",
                entity_type="processing_attempt",
                entity_id=str(attempt_id),
                payload={},
            )
        )
        await self.session.commit()
        return attempt.raw_request_encrypted, attempt.raw_payload_encrypted
