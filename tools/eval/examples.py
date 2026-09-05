"""Какие размеченные посты показать модели как образцы.

Сейчас ядро отдаёт восемь самых свежих ручных разметок (`select_recent`).
Гипотеза измерителя — ближайшие по смыслу (`select_knn`) работают лучше.
Оба отбора исключают сам классифицируемый пост: иначе ответ был бы в
подсказке.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import numpy as np
from thirdnews_contracts import LabeledExample

from .dataset import Record

#: Как в services/main/app/knowledge.py: образец решения, а не весь текст.
EXAMPLE_BODY_CHARS = 700

DEFAULT_MODEL = "intfloat/multilingual-e5-base"


def to_example(record: Record) -> LabeledExample:
    labels = {
        slug: list(record.labels.get(slug, []))
        for slug in record.manual_facets
        if record.labels.get(slug)
    }
    body = record.body_md[:EXAMPLE_BODY_CHARS]
    if len(record.body_md) > EXAMPLE_BODY_CHARS:
        body += "…"
    return LabeledExample(title=record.title, body_md=body, labels=labels)


def select_recent(target: Record, pool: list[Record], k: int) -> list[Record]:
    others = [r for r in pool if r.id != target.id]
    others.sort(
        key=lambda r: (
            r.published_at is not None,
            r.published_at.timestamp() if r.published_at else 0.0,
        ),
        reverse=True,
    )
    return others[:k]


class Embedder:
    """`embed` возвращает матрицу (n, d) с единичными строками."""

    def embed(self, texts: list[str]) -> np.ndarray:  # pragma: no cover - интерфейс
        raise NotImplementedError


def _normalise(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return matrix / norms


class FakeEmbedder(Embedder):
    """Мешок слов через хэширование — детерминированно и без моделей.

    Для тестов и для прогона измерителя на машине без torch.
    """

    def __init__(self, dim: int = 256) -> None:
        self.dim = dim

    def embed(self, texts: list[str]) -> np.ndarray:
        matrix = np.zeros((len(texts), self.dim), dtype=np.float32)
        for row, text in enumerate(texts):
            for token in re.findall(r"\w+", text.lower()):
                digest = hashlib.md5(token.encode("utf-8")).digest()
                matrix[row, int.from_bytes(digest[:4], "little") % self.dim] += 1.0
        return _normalise(matrix)


class E5Embedder(Embedder):
    """`intfloat/multilingual-e5-*` через sentence-transformers, лениво."""

    def __init__(self, model_name: str = DEFAULT_MODEL) -> None:
        self.model_name = model_name
        self._model = None

    def _load(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model_name)
        return self._model

    def embed(self, texts: list[str]) -> np.ndarray:
        # e5 обучена с префиксами; для сравнения «пост с постом» подходит query:.
        prefixed = [f"query: {text}" for text in texts]
        vectors = self._load().encode(prefixed, normalize_embeddings=True, batch_size=32)
        return np.asarray(vectors, dtype=np.float32)


class CachedEmbedder(Embedder):
    """Кэш векторов на диске по хэшу текста: 300 постов считаются один раз."""

    def __init__(self, inner: Embedder, cache_dir: Path) -> None:
        self.inner = inner
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, text: str) -> Path:
        return self.cache_dir / (hashlib.sha256(text.encode("utf-8")).hexdigest() + ".json")

    def embed(self, texts: list[str]) -> np.ndarray:
        result: list[np.ndarray | None] = [None] * len(texts)
        missing: list[int] = []
        for index, text in enumerate(texts):
            path = self._path(text)
            if path.exists():
                result[index] = np.asarray(json.loads(path.read_text()), dtype=np.float32)
            else:
                missing.append(index)
        if missing:
            fresh = self.inner.embed([texts[i] for i in missing])
            for row, index in enumerate(missing):
                result[index] = fresh[row]
                self._path(texts[index]).write_text(json.dumps(fresh[row].tolist()))
        return np.vstack(result)  # type: ignore[arg-type]


def select_knn(target: Record, pool: list[Record], k: int, embedder: Embedder) -> list[Record]:
    others = [r for r in pool if r.id != target.id]
    if not others or k <= 0:
        return []
    vectors = embedder.embed([target.text] + [r.text for r in others])
    scores = vectors[1:] @ vectors[0]
    order = np.argsort(-scores, kind="stable")[:k]
    return [others[i] for i in order]
