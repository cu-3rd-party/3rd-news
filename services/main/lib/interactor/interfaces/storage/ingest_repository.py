from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Protocol


class IngestRepository(Protocol):
    async def submission(self, submission_id: uuid.UUID) -> Any | None: ...

    async def create_upload_intent(
        self,
        *,
        owner_id: str,
        temporary_key: str,
        expected_size: int,
        content_type: str,
        sha256: str | None,
        expires_at: datetime,
    ) -> Any: ...

    async def lock_upload_intent(self, upload_id: uuid.UUID) -> Any | None: ...

    async def commit(self) -> None: ...
