import uuid
from datetime import datetime
from typing import Any, Protocol


class AuthAccountStorage(Protocol):
    async def find_user_by_email(self, email: str) -> Any | None: ...

    async def create_session(
        self,
        *,
        user_id: uuid.UUID,
        token_hash: str,
        csrf_hash: str,
        expires_at: datetime,
    ) -> None: ...

    async def find_session_by_hash(self, token_hash: str) -> Any | None: ...

    async def commit(self) -> None: ...
