import json
from typing import Any

from thirdnews_contracts import ClassifyRequest, Evidence, ProposedLabel


def json_content(content: object) -> dict[str, Any]:
    if isinstance(content, list):
        content = "".join(str(item.get("text", "")) for item in content if isinstance(item, dict))
    if not isinstance(content, str) or not content.strip():
        raise ValueError("provider response has no content")
    parsed = json.loads(content)
    if not isinstance(parsed, dict):
        raise TypeError("provider response is not an object")
    return parsed


def content(response: dict[str, Any]) -> dict[str, Any]:
    native_message = response.get("message")
    if isinstance(native_message, dict):
        return json_content(native_message.get("content"))
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("provider response has no choices")
    message = choices[0].get("message") or {}
    return json_content(message.get("content"))


def labels(request: ClassifyRequest, parsed: dict[str, Any]) -> list[ProposedLabel]:
    allowed_axes = set(request.options.allowed_axes) or {
        axis.slug for axis in request.taxonomy.facets
    }
    allowed_values = {
        axis.slug: {value.slug for value in axis.values}
        for axis in request.taxonomy.facets
        if axis.slug in allowed_axes
    }
    single = {axis.slug for axis in request.taxonomy.facets if axis.type.value == "single"}
    seen_single: set[str] = set()
    result: list[ProposedLabel] = []
    for raw in parsed.get("labels", []):
        if not isinstance(raw, dict):
            continue
        axis = str(raw.get("axis", ""))
        value = str(raw.get("value", ""))
        if axis not in allowed_axes or value not in allowed_values.get(axis, set()):
            continue
        if axis in single and axis in seen_single:
            continue
        try:
            confidence = max(0.0, min(1.0, float(raw.get("confidence", 0))))
        except TypeError, ValueError:
            continue
        if confidence < request.options.min_confidence:
            continue
        seen_single.add(axis)
        excerpt = str(raw.get("evidence") or "")[:1000] or None
        result.append(
            ProposedLabel(
                axis=axis,
                value=value,
                confidence=confidence,
                reason=str(raw.get("reason") or "")[:1000] or None,
                evidence=[Evidence(kind="model", excerpt=excerpt)] if excerpt else [],
            )
        )
    return result


def parse_response(request: ClassifyRequest, response: dict[str, Any]) -> list[ProposedLabel]:
    return labels(request, content(response))
