import importlib
from typing import Any

import numpy as np

from ...interactor.interfaces.clients.embedder import Embedder

DEFAULT_MODEL = "intfloat/multilingual-e5-base"


class E5Embedder(Embedder):
    def __init__(self, model_name: str = DEFAULT_MODEL) -> None:
        self.model_name = model_name
        self._model: Any = None

    def load(self) -> Any:
        if self._model is None:
            module = importlib.import_module("sentence_transformers")
            self._model = module.SentenceTransformer(self.model_name)
        return self._model

    def embed(self, texts: list[str]) -> np.ndarray:
        vectors = self.load().encode(
            [f"query: {text}" for text in texts],
            normalize_embeddings=True,
            batch_size=32,
        )
        return np.asarray(vectors, dtype=np.float32)
