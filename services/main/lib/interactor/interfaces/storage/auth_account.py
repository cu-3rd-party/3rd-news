import uuid
from datetime import datetime, timedelta
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

    async def auth_rate_limited(
        self, rate_keys: list[tuple[str, str]], moment: datetime
    ) -> bool: ...

    async def record_auth_failure(
        self,
        rate_keys: list[tuple[str, str]],
        *,
        moment: datetime,
        attempt_limit: int,
        window: timedelta,
        base_cooldown: timedelta,
        max_cooldown: timedelta,
    ) -> None: ...

    async def clear_account_auth_failures(self, identifier_hash: str) -> None: ...

    async def commit(self) -> None: ...
