from abc import ABC, abstractmethod
from typing import Any

from .embedder import Embedder


class EvaluationRuntime(ABC):
    @abstractmethod
    def load_classifiers(self) -> tuple[Any, Any]:
        raise NotImplementedError

    @abstractmethod
    def embedder(self, kind: str, model: str, cache_path: str) -> Embedder:
        raise NotImplementedError
