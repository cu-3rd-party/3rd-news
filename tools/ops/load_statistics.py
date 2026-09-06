import math
import statistics


def percentile(values: list[float], percentile_value: float) -> float:
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * percentile_value
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def latency_summary(values: list[float]) -> dict[str, float]:
    return {
        "p50": round(statistics.median(values), 2),
        "p95": round(percentile(values, 0.95), 2),
        "max": round(max(values), 2),
    }
