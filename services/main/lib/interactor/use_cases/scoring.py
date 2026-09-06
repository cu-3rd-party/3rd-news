from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

_DIMENSIONS = ("urgency", "impact", "editorial_priority")


@dataclass(frozen=True, slots=True)
class EditorialScores:
    urgency: int = 0
    impact: int = 0
    editorial_priority: int = 0

    @property
    def importance(self) -> int:
        return self.urgency + self.impact + self.editorial_priority


def evaluate_scores(
    labels: Mapping[str, Sequence[str]],
    rules: Sequence[Mapping[str, Any]],
    *,
    initial: EditorialScores | None = None,
) -> EditorialScores:

    scores = {name: getattr(initial or EditorialScores(), name) for name in _DIMENSIONS}
    ordered = sorted(
        (rule for rule in rules if rule.get("enabled", True)),
        key=lambda rule: (int(rule.get("priority", 100)), str(rule.get("id", ""))),
    )
    for rule in ordered:
        when = rule.get("when", {})
        if not isinstance(when, Mapping) or not _matches(labels, when):
            continue
        assignments = rule.get("set", {})
        additions = rule.get("add", {})
        if isinstance(assignments, Mapping):
            for dimension in _DIMENSIONS:
                if dimension in assignments:
                    scores[dimension] = _score(assignments[dimension])
        if isinstance(additions, Mapping):
            for dimension in _DIMENSIONS:
                if dimension in additions:
                    scores[dimension] = _score(scores[dimension] + int(additions[dimension]))
        if rule.get("stop") is True:
            break
    return EditorialScores(**scores)


def _matches(labels: Mapping[str, Sequence[str]], conditions: Mapping[str, Any]) -> bool:
    for axis, expected in conditions.items():
        actual = set(labels.get(str(axis), ()))
        accepted = {expected} if isinstance(expected, str) else set(expected or ())
        if not actual.intersection(str(value) for value in accepted):
            return False
    return True


def _score(value: Any) -> int:
    return min(max(int(value), 0), 100)
