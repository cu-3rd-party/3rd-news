import hashlib
import json
from pathlib import Path

import numpy as np

from ...interactor.interfaces.clients.embedder import Embedder


class CachedEmbedder(Embedder):
    def __init__(self, inner: Embedder, cache_dir: Path) -> None:
        self.inner = inner
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def path(self, text: str) -> Path:
        return self.cache_dir / f"{hashlib.sha256(text.encode()).hexdigest()}.json"

    def embed(self, texts: list[str]) -> np.ndarray:
        result: list[np.ndarray | None] = [None] * len(texts)
        missing: list[int] = []
        for index, text in enumerate(texts):
            path = self.path(text)
            if path.exists():
                result[index] = np.asarray(json.loads(path.read_text()), dtype=np.float32)
            else:
                missing.append(index)
        if missing:
            fresh = self.inner.embed([texts[index] for index in missing])
            for row, index in enumerate(missing):
                result[index] = fresh[row]
                self.path(texts[index]).write_text(json.dumps(fresh[row].tolist()))
        completed = [item for item in result if item is not None]
        if len(completed) != len(result):
            raise RuntimeError("embedding cache did not produce every vector")
        return np.vstack(completed)
