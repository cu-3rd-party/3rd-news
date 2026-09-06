from typing import Any

from ...core.config import Settings


def trace_parameters(settings: Settings, payload: dict[str, Any]) -> dict[str, Any]:
    if settings.provider_protocol == "openai":
        return {
            key: payload[key]
            for key in ("temperature", "max_tokens", "reasoning_effort")
            if key in payload
        } | {
            "protocol": "openai",
            "response_format": payload["response_format"]["type"],
        }
    options = payload.get("options")
    safe_options = options if isinstance(options, dict) else {}
    return {
        "protocol": "ollama-native",
        "response_format": settings.openai_response_format,
        "think": payload.get("think"),
        "temperature": safe_options.get("temperature"),
        "max_tokens": safe_options.get("num_predict"),
        "num_ctx": safe_options.get("num_ctx"),
        "num_thread": safe_options.get("num_thread"),
    }
