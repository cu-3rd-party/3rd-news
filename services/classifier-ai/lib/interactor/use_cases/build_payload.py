import json
from typing import Any

from thirdnews_contracts import ClassifyRequest

from ...core.config import Settings
from ...domain.entities.response_schema import RESPONSE_SCHEMA, SYSTEM_PROMPT


def taxonomy_payload(request: ClassifyRequest) -> list[dict[str, Any]]:
    allowed = set(request.options.allowed_axes)
    return [
        {
            "axis": axis.slug,
            "title": axis.title,
            "type": axis.type.value,
            "required": axis.required,
            "description": axis.ai_hint or axis.description,
            "values": [
                {
                    "value": value.slug,
                    "title": value.title,
                    "description": value.ai_hint or value.description,
                    "synonyms": value.synonyms,
                }
                for value in axis.values
            ],
        }
        for axis in request.taxonomy.facets
        if not allowed or axis.slug in allowed
    ]


def build_payload(request: ClassifyRequest, settings: Settings) -> dict[str, Any]:
    config = request.options.config
    model = str(config.get("model") or settings.openai_model)
    prompt = {
        "context": request.context,
        "taxonomy": taxonomy_payload(request),
        "examples": [example.model_dump(mode="json") for example in request.examples],
        "news": {
            "title": request.news.title,
            "body_md": request.news.body_md[: settings.max_body_chars],
            "source": request.news.source_text or request.news.source_link,
            "attachments": [
                {
                    "kind": item.kind,
                    "caption": item.caption,
                    "extracted_text": item.extracted_text,
                }
                for item in request.news.attachments
            ],
        },
    }
    response_format = str(config.get("response_format") or settings.openai_response_format)
    if response_format not in {"json_schema", "json_object"}:
        raise ValueError("response_format must be json_schema or json_object")
    reasoning_effort = config.get("reasoning_effort", settings.openai_reasoning_effort)
    user_content = json.dumps(prompt, ensure_ascii=False)
    if reasoning_effort == "none":
        user_content = f"/no_think\n{user_content}"
    payload = {
        "model": model,
        "temperature": float(config.get("temperature", 0.0)),
        "max_tokens": int(config.get("max_tokens", settings.max_output_tokens)),
        "messages": [
            {"role": "system", "content": str(config.get("system_prompt") or SYSTEM_PROMPT)},
            {"role": "user", "content": user_content},
        ],
        "response_format": (
            {"type": "json_schema", "json_schema": RESPONSE_SCHEMA}
            if response_format == "json_schema"
            else {"type": "json_object"}
        ),
    }
    if reasoning_effort is not None:
        payload["reasoning_effort"] = str(reasoning_effort)
    if settings.provider_protocol == "openai":
        return payload
    return {
        "model": model,
        "stream": False,
        "think": reasoning_effort != "none",
        "messages": payload["messages"],
        "format": RESPONSE_SCHEMA["schema"] if response_format == "json_schema" else "json",
        "options": {
            "temperature": payload["temperature"],
            "num_predict": payload["max_tokens"],
            "num_thread": settings.ollama_num_threads,
            "num_ctx": settings.ollama_num_ctx,
        },
    }
