from typing import Any, Protocol


class AuthenticationClient(Protocol):
    def bind_database(
        self, session_factory: Any, *, api_key_touch_interval_seconds: int
    ) -> None: ...

    async def resolve_trusted_proxy_hosts(
        self, hosts: list[str], *, timeout_seconds: float
    ) -> None: ...

    async def authenticate(self, request: Any, session: Any) -> Any | None: ...

    def hash_password(self, password: str) -> str: ...
