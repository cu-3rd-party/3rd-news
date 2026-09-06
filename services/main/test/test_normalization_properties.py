import math

from hypothesis import given, settings
from hypothesis import strategies as st
from lib.domain import Importance
from lib.interactor.use_cases.processing.normalization import AxisDefinition, normalize_labels

label = st.fixed_dictionaries(
    {
        "axis": st.sampled_from(["single", "multi", "forbidden", "unknown"]),
        "value": st.sampled_from(["a", "b", "unknown"]),
        "confidence": st.one_of(st.floats(), st.none(), st.text(max_size=10)),
    }
)


@given(st.lists(label, max_size=80))
@settings(max_examples=250, deadline=None, derandomize=True)
def test_hostile_labels_cannot_expand_axes_or_cardinality(labels):
    axes = {
        "single": AxisDefinition("single", frozenset({"a", "b"})),
        "multi": AxisDefinition("multi", frozenset({"a", "b"}), multiple=True),
        "forbidden": AxisDefinition("forbidden", frozenset({"a", "b"})),
    }
    result = normalize_labels(labels, axes=axes, allowed_axes=["single", "multi"])
    reverse = normalize_labels(reversed(labels), axes=axes, allowed_axes=["single", "multi"])
    assert result == reverse
    assert sum(item.axis == "single" for item in result) <= 1
    assert len({(item.axis, item.value) for item in result}) == len(result)
    assert all(item.axis in {"single", "multi"} for item in result)
    assert all(item.value in {"a", "b"} for item in result)
    assert all(math.isfinite(item.confidence) and 0 <= item.confidence <= 1 for item in result)


@given(st.integers(0, 100), st.integers(0, 100), st.integers(0, 100))
@settings(max_examples=250, derandomize=True)
def test_generated_score_components_remain_bounded(urgency, impact, priority):
    importance = Importance(urgency, impact, priority)
    assert importance.total == sum((urgency, impact, priority))
    assert 0 <= importance.total <= 300
