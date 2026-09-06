from __future__ import annotations

from dataclasses import asdict
from itertools import pairwise

from thirdnews_contracts import FacetSchema, Taxonomy

from ...domain.entities.facet_report import FacetReport
from ...domain.entities.prediction import Prediction
from ...domain.entities.record import Record
from .eval_dataset import gold_labels


def _prf(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return (precision, recall, f1)


def facet_metrics(facet: FacetSchema, pairs: list[tuple[set[str], set[str]]]) -> FacetReport:
    per_value: dict[str, dict[str, float]] = {}
    for value in facet.values:
        slug = value.slug
        tp = sum((1 for gold, pred in pairs if slug in gold and slug in pred))
        fp = sum((1 for gold, pred in pairs if slug not in gold and slug in pred))
        fn = sum((1 for gold, pred in pairs if slug in gold and slug not in pred))
        precision, recall, f1 = _prf(tp, fp, fn)
        per_value[slug] = {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "support": float(tp + fn),
        }
    exact = sum((1 for gold, pred in pairs if gold == pred)) / len(pairs) if pairs else 0.0
    scored = [m["f1"] for m in per_value.values() if m["support"] > 0]
    macro_f1 = sum(scored) / len(scored) if scored else 0.0
    return FacetReport(
        facet=facet.slug,
        type=facet.type.value,
        n=len(pairs),
        exact=exact,
        macro_f1=macro_f1,
        per_value=per_value,
    )


def calibration(
    items: list[tuple[float, bool]], bins: tuple[float, ...] = (0.5, 0.6, 0.7, 0.8, 0.9, 1.0001)
) -> list[dict]:
    report = []
    for lo, hi in pairwise(bins):
        inside = [correct for confidence, correct in items if lo <= confidence < hi]
        report.append(
            {
                "lo": lo,
                "hi": min(hi, 1.0),
                "n": len(inside),
                "accuracy": sum(inside) / len(inside) if inside else None,
            }
        )
    return report


def summarize(
    records: list[Record], predictions: dict[str, Prediction], taxonomy: Taxonomy
) -> dict:
    facets: list[dict] = []
    confidence_items: list[tuple[float, bool]] = []
    for facet in taxonomy.facets:
        pairs: list[tuple[set[str], set[str]]] = []
        for record in records:
            gold = gold_labels(record, facet.slug)
            if gold is None:
                continue
            predicted = predictions[record.id].labels.get(facet.slug, [])
            pairs.append((gold, {value for value, _confidence in predicted}))
            confidence_items.extend(
                ((confidence, value in gold) for value, confidence in predicted)
            )
        facets.append(asdict(facet_metrics(facet, pairs)))
    used = [predictions[record.id] for record in records]
    return {
        "n": len(records),
        "facets": facets,
        "calibration": calibration(confidence_items),
        "avg_latency_s": sum(p.latency_s for p in used) / len(used) if used else 0.0,
        "prompt_tokens": sum(p.prompt_tokens for p in used),
        "completion_tokens": sum(p.completion_tokens for p in used),
        "cache_hits": sum(1 for p in used if p.cached),
    }
