from typing import Any, Protocol


class BootstrapStorage(Protocol):
    async def initialize(
        self,
        *,
        admin_email: str,
        admin_password_hash: str | None,
        classifiers: list[dict[str, Any]],
    ) -> None: ...
