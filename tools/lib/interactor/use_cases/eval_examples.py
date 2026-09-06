from __future__ import annotations

import numpy as np
from thirdnews_contracts import LabeledExample

from ...domain.entities.record import Record
from ..interfaces.clients.embedder import Embedder

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


def _normalise(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return matrix / norms


def select_knn(target: Record, pool: list[Record], k: int, embedder: Embedder) -> list[Record]:
    others = [r for r in pool if r.id != target.id]
    if not others or k <= 0:
        return []
    vectors = embedder.embed([target.text] + [r.text for r in others])
    scores = vectors[1:] @ vectors[0]
    order = np.argsort(-scores, kind="stable")[:k]
    return [others[i] for i in order]
