from __future__ import annotations

import pytest
from lib.domain import Importance, SubmissionIdentity


@pytest.mark.parametrize(
    ("urgency", "impact", "editorial_priority", "total"),
    [(0, 0, 0, 0), (50, 50, 50, 150), (100, 100, 100, 300)],
)
def test_importance_is_deterministic(urgency, impact, editorial_priority, total) -> None:
    value = Importance(urgency, impact, editorial_priority)
    assert value.total == total


@pytest.mark.parametrize("field", [-1, 101])
def test_importance_rejects_out_of_range_values(field) -> None:
    with pytest.raises(ValueError):
        Importance(field, 50, 50)


def test_submission_identity_requires_complete_source_pair_or_idempotency() -> None:
    for incomplete in (
        (None, None, None),
        ("source", None, None),
        (None, "42", None),
        ("", "42", None),
        ("source", "", None),
    ):
        with pytest.raises(ValueError):
            SubmissionIdentity(*incomplete)

    assert SubmissionIdentity("source", "42", None).external_id == "42"
    assert SubmissionIdentity(None, None, "request-42").idempotency_key == "request-42"
    assert SubmissionIdentity("source", "42", "request-42").external_id == "42"
