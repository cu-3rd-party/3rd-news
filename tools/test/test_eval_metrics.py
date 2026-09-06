from __future__ import annotations

from pathlib import Path

import pytest
from tools.lib.interactor.use_cases.eval_dataset import load_records, load_taxonomy
from tools.lib.interactor.use_cases.eval_metrics import calibration, facet_metrics, summarize
from tools.lib.interactor.use_cases.eval_runners import Prediction

FIX = Path(__file__).parent / "fixtures"


def test_single_facet_exact_match_counts_empty_as_correct():
    taxonomy = load_taxonomy(FIX / "eval_taxonomy.json")
    facet = taxonomy.facet("importance")
    assert facet is not None
    pairs = [({"critical"}, {"critical"}), ({"normal"}, {"critical"}), (set(), set())]
    report = facet_metrics(facet, pairs)
    assert report.n == 3
    assert report.exact == pytest.approx(2 / 3)
    assert report.per_value["critical"]["precision"] == pytest.approx(0.5)
    assert report.per_value["critical"]["recall"] == pytest.approx(1.0)
    assert report.per_value["normal"]["recall"] == pytest.approx(0.0)


def test_multi_facet_f1_per_value():
    taxonomy = load_taxonomy(FIX / "eval_taxonomy.json")
    facet = taxonomy.facet("stream")
    assert facet is not None
    pairs = [({"2025", "2026"}, {"2025"}), ({"2026"}, {"2026"}), (set(), {"2025"})]
    report = facet_metrics(facet, pairs)
    assert report.per_value["2025"]["precision"] == pytest.approx(0.5)
    assert report.per_value["2025"]["recall"] == pytest.approx(1.0)
    assert report.per_value["2026"]["f1"] == pytest.approx(2 / 3)
    assert report.exact == pytest.approx(1 / 3)


def test_calibration_bins():
    items = [(0.55, False), (0.65, True), (0.68, False), (0.95, True), (0.99, True)]
    bins = calibration(items)
    by_lo = {b["lo"]: b for b in bins}
    assert by_lo[0.5]["n"] == 1 and by_lo[0.5]["accuracy"] == 0.0
    assert by_lo[0.6]["n"] == 2 and by_lo[0.6]["accuracy"] == pytest.approx(0.5)
    assert by_lo[0.9]["n"] == 2 and by_lo[0.9]["accuracy"] == 1.0
    assert by_lo[0.7]["accuracy"] is None


def test_summarize_skips_untouched_facets_and_aggregates_cost():
    records = load_records(FIX / "eval_gold.jsonl")
    taxonomy = load_taxonomy(FIX / "eval_taxonomy.json")
    predictions = {
        r.id: Prediction(
            labels={"importance": [("critical", 0.9)], "stream": [("2025", 0.8)]},
            latency_s=1.0,
            prompt_tokens=100,
            completion_tokens=10,
            cached=(r.id != "n1"),
        )
        for r in records
    }
    summary = summarize(records, predictions, taxonomy)
    stream = next(f for f in summary["facets"] if f["facet"] == "stream")
    assert stream["n"] == 4
    assert summary["n"] == 5
    assert summary["prompt_tokens"] == 500
    assert summary["cache_hits"] == 4
    assert summary["avg_latency_s"] == pytest.approx(1.0)
