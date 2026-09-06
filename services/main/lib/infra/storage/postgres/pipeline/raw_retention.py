from datetime import UTC, datetime, timedelta

from lib.domain import PipelineRuntime
from lib.infra.storage.postgres.models import ProcessingAttempt
from sqlalchemy import or_, update


class PipelineRawRetention:
    async def purge(self, runtime: PipelineRuntime) -> int:
        cutoff = datetime.now(UTC) - timedelta(days=runtime.raw_retention_days)
        async with runtime.sessions() as session, session.begin():
            result = await session.execute(
                update(ProcessingAttempt)
                .where(
                    ProcessingAttempt.started_at < cutoff,
                    or_(
                        ProcessingAttempt.raw_request_encrypted.is_not(None),
                        ProcessingAttempt.raw_payload_encrypted.is_not(None),
                    ),
                )
                .values(raw_request_encrypted=None, raw_payload_encrypted=None)
            )
            return int(getattr(result, "rowcount", 0) or 0)
