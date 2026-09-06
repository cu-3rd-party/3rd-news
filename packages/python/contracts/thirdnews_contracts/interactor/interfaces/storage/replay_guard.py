from typing import Protocol


class ReplayGuard(Protocol):
    def __call__(self, token_id: str, expires_at: int) -> bool: ...
