import hashlib
import re

import numpy as np

from ...interactor.interfaces.clients.embedder import Embedder
from .normalise import normalise


class FakeEmbedder(Embedder):
    def __init__(self, dim: int = 256) -> None:
        self.dim = dim

    def embed(self, texts: list[str]) -> np.ndarray:
        matrix = np.zeros((len(texts), self.dim), dtype=np.float32)
        for row, text in enumerate(texts):
            for token in re.findall(r"\w+", text.lower()):
                digest = hashlib.md5(token.encode()).digest()
                matrix[row, int.from_bytes(digest[:4], "little") % self.dim] += 1.0
        return normalise(matrix)
