from __future__ import annotations

import csv
import json
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from tools.lib.core.config import Settings
from tools.lib.handlers.evaluation import blind, compare, kappa, run
from tools.lib.interactor.use_cases.eval_dataset import load_records

FIX = Path(__file__).parent / "fixtures"


def test_run_regex_with_knn_fake_embedder_and_compare(tmp_path: Path) -> None:
    output = tmp_path / "regex.json"
    settings = Settings.model_validate(
        {
            "eval_data_path": FIX / "eval_gold.jsonl",
            "eval_taxonomy_path": FIX / "eval_taxonomy.json",
            "eval_classifier": "regex",
            "eval_examples": "knn",
            "eval_k": 2,
            "eval_embedder": "fake",
            "eval_cache_path": tmp_path / "cache",
            "eval_output_path": output,
        }
    )
    assert run(settings) == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["params"]["eval_classifier"] == "regex"
    facets = {facet["facet"]: facet for facet in payload["summary"]["facets"]}
    assert facets["importance"]["n"] == 5
    assert (tmp_path / "cache" / "emb" / "fake").exists()
    stream = StringIO()
    with redirect_stdout(stream):
        assert compare(Settings.model_validate({"eval_result_paths": [output]})) == 0
    assert "importance" in stream.getvalue()
    assert "regex" in stream.getvalue()


def test_blind_and_kappa_round_trip(tmp_path: Path) -> None:
    blind_path = tmp_path / "blind.csv"
    settings = Settings.model_validate(
        {
            "eval_data_path": FIX / "eval_gold.jsonl",
            "eval_taxonomy_path": FIX / "eval_taxonomy.json",
            "eval_sample_size": 2,
            "eval_seed": 1,
            "eval_output_path": blind_path,
        }
    )
    assert blind(settings) == 0
    records = {record.id: record for record in load_records(FIX / "eval_gold.jsonl")}
    rows = list(csv.DictReader(blind_path.open(encoding="utf-8")))
    for row in rows:
        for facet in ("importance", "stream"):
            if facet in records[row["id"]].manual_facets:
                row[facet] = ";".join(records[row["id"]].labels.get(facet, [])) or "-"
    friend = tmp_path / "friend.csv"
    with friend.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    stream = StringIO()
    with redirect_stdout(stream):
        assert kappa(settings.model_copy(update={"eval_other_path": friend})) == 0
    assert "importance" in stream.getvalue()
    assert "расхождений=0" in stream.getvalue()
