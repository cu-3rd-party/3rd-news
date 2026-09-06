from collections.abc import Awaitable
from typing import Any


class DeferredClassification:
    def __init__(self, result: Awaitable[Any]) -> None:
        self.result = result
