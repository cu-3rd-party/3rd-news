from typing import Any, Protocol

from lib.dto.accepted_submission import AcceptedSubmission
from lib.interactor.interfaces.storage.labels import LabelStorage


class SubmissionWriterStorage(Protocol):
    async def write(
        self,
        uow: Any,
        payload: Any,
        raw: dict[str, Any],
        digest: str,
        source_slug: str | None,
        external_id: str | None,
        idempotency_key: str | None,
        principal_id: str,
        bound_source_id: Any,
        cooldown_seconds: float,
        max_attempts: int,
        label_storage: LabelStorage,
    ) -> AcceptedSubmission: ...
