from __future__ import annotations

import json
from pathlib import Path

from tools.lib.interactor.use_cases.eval_dataset import (
    gold_labels,
    load_context,
    load_records,
    load_taxonomy,
)

FIX = Path(__file__).parent / "fixtures"


def test_records_are_loaded_in_publication_order():
    records = load_records(FIX / "eval_gold.jsonl")
    assert [r.id for r in records] == ["n1", "n2", "n3", "n4", "n5"]
    assert records[0].labels == {"importance": ["critical"], "stream": ["2025"]}
    assert records[4].is_gold is True


def test_record_text_joins_title_and_body():
    records = load_records(FIX / "eval_gold.jsonl")
    assert records[0].text.startswith("Дедлайн по курсовой\n")
    assert records[3].text == "Афиша."


def test_gold_labels_distinguish_empty_from_untouched():
    records = {r.id: r for r in load_records(FIX / "eval_gold.jsonl")}
    assert gold_labels(records["n2"], "stream") == set()
    assert gold_labels(records["n4"], "stream") is None
    assert gold_labels(records["n1"], "stream") == {"2025"}


def test_taxonomy_from_admin_facets_list():
    taxonomy = load_taxonomy(FIX / "eval_taxonomy.json")
    assert [f.slug for f in taxonomy.facets] == ["importance", "stream"]
    stream = taxonomy.facet("stream")
    importance = taxonomy.facet("importance")
    assert stream is not None and stream.type.value == "multi"
    assert importance is not None and importance.values[0].synonyms == ["срочно", "дедлайн"]


def test_taxonomy_drops_inactive(tmp_path):
    data = json.loads((FIX / "eval_taxonomy.json").read_text(encoding="utf-8"))
    data[1]["is_active"] = False
    data[0]["values"][1]["is_active"] = False
    path = tmp_path / "t.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    taxonomy = load_taxonomy(path)
    assert [f.slug for f in taxonomy.facets] == ["importance"]
    assert [v.slug for v in taxonomy.facets[0].values] == ["critical"]


def test_context_is_optional(tmp_path):
    assert load_context(None) is None
    path = tmp_path / "context.md"
    path.write_text("  ЦУ — Центральный университет.  ", encoding="utf-8")
    assert load_context(path) == "ЦУ — Центральный университет."
