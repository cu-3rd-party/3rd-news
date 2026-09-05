"""CLI измерителя — сквозной прогон regex на фикстуре, без сети."""

from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

from tools.eval.dataset import load_records

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures"


def _run(*args):
    return subprocess.run(
        [sys.executable, "-m", "tools.eval", *args], cwd=ROOT, capture_output=True, text=True
    )


def test_run_regex_with_knn_fake_embedder_and_compare(tmp_path):
    out = tmp_path / "regex.json"
    result = _run(
        "run",
        "--data", str(FIX / "eval_gold.jsonl"),
        "--taxonomy", str(FIX / "eval_taxonomy.json"),
        "--classifier", "regex",
        "--examples", "knn", "--k", "2", "--embedder", "fake",
        "--cache-dir", str(tmp_path / "cache"),
        "--out", str(out),
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["params"]["classifier"] == "regex"
    facets = {f["facet"]: f for f in payload["summary"]["facets"]}
    assert facets["importance"]["n"] == 5
    assert (tmp_path / "cache" / "emb" / "fake").exists()

    table = _run("compare", str(out))
    assert table.returncode == 0, table.stderr
    assert "importance" in table.stdout and "regex" in table.stdout


def test_blind_and_kappa_round_trip(tmp_path):
    blind = tmp_path / "blind.csv"
    result = _run(
        "blind",
        "--data", str(FIX / "eval_gold.jsonl"),
        "--taxonomy", str(FIX / "eval_taxonomy.json"),
        "--n", "2", "--seed", "1",
        "--out", str(blind),
    )
    assert result.returncode == 0, result.stderr

    # Друг «разметил» так же, как эталон: копируем метки из набора.
    records = {r.id: r for r in load_records(FIX / "eval_gold.jsonl")}
    rows = list(csv.DictReader(blind.open(encoding="utf-8")))
    for row in rows:
        for facet in ("importance", "stream"):
            if facet in records[row["id"]].manual_facets:
                row[facet] = ";".join(records[row["id"]].labels.get(facet, [])) or "-"
    friend = tmp_path / "friend.csv"
    with friend.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    result = _run(
        "kappa",
        "--data", str(FIX / "eval_gold.jsonl"),
        "--taxonomy", str(FIX / "eval_taxonomy.json"),
        "--other", str(friend),
    )
    assert result.returncode == 0, result.stderr
    assert "importance" in result.stdout
    assert "расхождений=0" in result.stdout
