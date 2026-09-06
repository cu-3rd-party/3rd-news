from __future__ import annotations

import csv
from pathlib import Path
from typing import cast

import pytest
from tools.lib.interactor.use_cases.eval_dataset import load_records, load_taxonomy
from tools.lib.interactor.use_cases.eval_kappa import (
    cohen_kappa,
    kappa_report,
    read_labels_csv,
    write_blind_csv,
)

FIX = Path(__file__).parent / "fixtures"


def test_kappa_perfect_and_chance():
    assert cohen_kappa(["a", "b", "a"], ["a", "b", "a"]) == pytest.approx(1.0)
    assert cohen_kappa(["a", "a", "b", "b"], ["a", "b", "a", "b"]) == pytest.approx(0.0)
    assert cohen_kappa(["a", "a"], ["a", "a"]) == pytest.approx(1.0)


def test_blind_csv_has_no_labels(tmp_path):
    records = load_records(FIX / "eval_gold.jsonl")
    taxonomy = load_taxonomy(FIX / "eval_taxonomy.json")
    path = tmp_path / "blind.csv"
    ids = write_blind_csv(records, taxonomy, path, n=3, seed=1)
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    assert len(rows) == 3 and [r["id"] for r in rows] == ids
    assert set(rows[0]) == {"id", "source_key", "title", "body_md", "importance", "stream"}
    assert all(r["importance"] == "" and r["stream"] == "" for r in rows)


def test_read_labels_csv_conventions(tmp_path):
    path = tmp_path / "friend.csv"
    path.write_text("id,importance,stream\nn1,critical,2025;2026\nn2,-,\n", encoding="utf-8")
    labels = read_labels_csv(path)
    assert labels["n1"] == {"importance": {"critical"}, "stream": {"2025", "2026"}}
    assert labels["n2"] == {"importance": set(), "stream": None}


def test_kappa_report_lists_disagreements():
    records = load_records(FIX / "eval_gold.jsonl")
    taxonomy = load_taxonomy(FIX / "eval_taxonomy.json")
    other = {
        "n1": {"importance": {"critical"}, "stream": {"2025"}},
        "n2": {"importance": {"critical"}, "stream": set()},
        "n3": {"importance": {"critical"}, "stream": {"2026"}},
    }
    report = kappa_report(records, cast(dict[str, dict[str, set[str] | None]], other), taxonomy)
    importance = report["importance"]
    assert importance["n"] == 3
    assert importance["disagreements"] == [{"id": "n2", "gold": ["normal"], "other": ["critical"]}]
    assert report["stream"]["disagreements"] == []
    assert report["stream"]["kappa"] == pytest.approx(1.0)
