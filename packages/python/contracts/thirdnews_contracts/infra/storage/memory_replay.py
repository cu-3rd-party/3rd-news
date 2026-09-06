import time

from ...interactor.interfaces.storage.replay import ReplayStorage


class MemoryReplayStorage(ReplayStorage):
    def __init__(self) -> None:
        self._tokens: dict[str, int] = {}

    def accept_once(self, token_id: str, expires_at: int) -> bool:
        current = int(time.time())
        for expired_id in [key for key, expiry in self._tokens.items() if expiry < current]:
            self._tokens.pop(expired_id, None)
        if token_id in self._tokens:
            return False
        self._tokens[token_id] = expires_at
        return True
