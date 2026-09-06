from pathlib import Path
from typing import Any

from ...interactor.interfaces.clients.embedder import Embedder
from ...interactor.interfaces.clients.evaluation_runtime import EvaluationRuntime
from ..storage.cached_embedder import CachedEmbedder
from .classifier_runtime import load_classifiers
from .e5_embedder import E5Embedder
from .fake_embedder import FakeEmbedder


class LocalEvaluationRuntime(EvaluationRuntime):
    def load_classifiers(self) -> tuple[Any, Any]:
        return load_classifiers()

    def embedder(self, kind: str, model: str, cache_path: str) -> Embedder:
        inner = FakeEmbedder() if kind == "fake" else E5Embedder(model)
        tag = "fake" if kind == "fake" else model.replace("/", "__")
        return CachedEmbedder(inner, Path(cache_path) / "emb" / tag)
