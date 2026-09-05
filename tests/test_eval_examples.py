"""Выбор примеров для few-shot: свежие и ближайшие."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from tools.eval.dataset import load_records
from tools.eval.examples import (
    CachedEmbedder,
    FakeEmbedder,
    select_knn,
    select_recent,
    to_example,
)

FIX = Path(__file__).parent / "fixtures"


def records():
    return load_records(FIX / "eval_gold.jsonl")


def test_recent_never_includes_the_target_and_is_newest_first():
    pool = records()
    target = pool[2]  # n3
    chosen = select_recent(target, pool, k=2)
    assert [r.id for r in chosen] == ["n5", "n4"]
    assert target.id not in [r.id for r in chosen]


def test_recent_k_larger_than_pool():
    pool = records()
    assert len(select_recent(pool[0], pool, k=99)) == 4


def test_to_example_keeps_only_touched_facets_and_trims():
    pool = records()
    example = to_example(pool[3])  # n4: только importance
    assert example.labels == {"importance": ["normal"]}
    long = pool[0]
    long.body_md = "x" * 1000
    assert len(to_example(long).body_md) == 701  # 700 + «…»


def test_knn_prefers_lexically_similar_posts():
    pool = records()
    target = pool[4]  # n5: пересдачи, второго курса, срочно
    chosen = select_knn(target, pool, k=2, embedder=FakeEmbedder())
    ids = [r.id for r in chosen]
    assert target.id not in ids
    assert ids[0] == "n1"  # тоже «срочно» и «второго курса»


def test_fake_embedder_rows_are_unit_length():
    vectors = FakeEmbedder().embed(["раз два", "три"])
    assert vectors.shape[0] == 2
    assert np.allclose(np.linalg.norm(vectors, axis=1), 1.0)


def test_cached_embedder_hits_disk_second_time(tmp_path):
    class Counting(FakeEmbedder):
        calls = 0

        def embed(self, texts):
            Counting.calls += len(texts)
            return super().embed(texts)

    cached = CachedEmbedder(Counting(), tmp_path)
    first = cached.embed(["а", "б"])
    second = cached.embed(["а", "б", "в"])
    assert Counting.calls == 3
    assert np.allclose(first, second[:2])
