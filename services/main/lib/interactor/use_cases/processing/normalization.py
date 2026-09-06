from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from typing import Any

from lib.domain import AxisDefinition, NormalizedLabel


def normalize_labels(
    labels: Iterable[Any],
    *,
    axes: Mapping[str, AxisDefinition],
    allowed_axes: Iterable[str],
    min_confidence: float = 0.0,
) -> tuple[NormalizedLabel, ...]:

    allowed = frozenset(allowed_axes)
    minimum = _finite_clamped(min_confidence)
    strongest: dict[tuple[str, str], NormalizedLabel] = {}
    for item in labels:
        axis = _field(item, "axis")
        value = _field(item, "value")
        definition = axes.get(axis) if isinstance(axis, str) else None
        if definition is None or axis not in allowed or value not in definition.values:
            continue
        confidence = _finite_clamped(_field(item, "confidence", 1.0))
        if confidence < minimum:
            continue
        reason_value = _field(item, "reason")
        reason = str(reason_value)[:1000] if reason_value else None
        raw_evidence = _field(item, "evidence", ()) or ()
        evidence = tuple(_as_mapping(entry) for entry in raw_evidence if _as_mapping(entry))
        candidate = NormalizedLabel(axis, value, confidence, reason, evidence[:50])
        key = (axis, value)
        previous = strongest.get(key)
        if previous is None or _rank(candidate) < _rank(previous):
            strongest[key] = candidate

    grouped: dict[str, list[NormalizedLabel]] = {}
    for label in strongest.values():
        grouped.setdefault(label.axis, []).append(label)
    normalized: list[NormalizedLabel] = []
    for axis in sorted(grouped):
        values = sorted(grouped[axis], key=_rank)
        normalized.extend(values if axes[axis].multiple else values[:1])
    return tuple(normalized)


def _field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _as_mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    dump = getattr(value, "model_dump", None)
    if not callable(dump):
        return {}
    result = dump(mode="json")
    return dict(result) if isinstance(result, Mapping) else {}


def _finite_clamped(value: Any) -> float:
    try:
        converted = float(value)
    except TypeError, ValueError:
        return 0.0
    if not math.isfinite(converted):
        return 0.0
    return min(max(converted, 0.0), 1.0)


def _rank(label: NormalizedLabel) -> tuple[float, str, str]:
    return (-label.confidence, label.value, label.reason or "")
