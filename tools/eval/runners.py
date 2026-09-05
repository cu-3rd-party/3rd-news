"""Вызов классификаторов в процессе и склейка их мнений по прод-правилу."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType

from thirdnews_contracts import (
    ClassifyAttachment,
    ClassifyNews,
    ClassifyOptions,
    ClassifyRequest,
    ProposedLabel,
    Taxonomy,
)

from .dataset import Record
from .examples import to_example

ROOT = Path(__file__).resolve().parents[2]

#: Как в scripts/register_classifiers.sh: правило редактора сильнее догадки модели.
REGEX_PRIORITY = 200
AI_PRIORITY = 100


def _load(service: str, alias: str) -> ModuleType:
    if alias in sys.modules:
        return sys.modules[alias]
    path = ROOT / "services" / service / "app" / "main.py"
    spec = importlib.util.spec_from_file_location(alias, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[alias] = module
    spec.loader.exec_module(module)
    return module


def load_classifiers() -> tuple[ModuleType, ModuleType]:
    """(regex, ai) — те же файлы, что крутятся в контейнерах."""

    return (
        _load("classifier-regex", "eval_classifier_regex"),
        _load("classifier-ai", "eval_classifier_ai"),
    )


def build_request(
    record: Record,
    taxonomy: Taxonomy,
    examples: list[Record],
    context: str | None,
    config: dict,
    min_confidence: float,
) -> ClassifyRequest:
    return ClassifyRequest(
        request_id=str(uuid.uuid4()),
        news=ClassifyNews(
            id=record.id,
            title=record.title,
            body_md=record.body_md,
            source_link=record.source_link,
            source_text=record.source_text,
            published_at=record.published_at,
            attachments=[
                ClassifyAttachment(
                    kind=item.get("kind", "file"),
                    mime=item.get("mime"),
                    filename=item.get("filename"),
                    caption=item.get("caption"),
                )
                for item in record.attachments
            ],
            extra=record.extra,
        ),
        taxonomy=taxonomy,
        context=context,
        examples=[to_example(example) for example in examples],
        options=ClassifyOptions(min_confidence=min_confidence, config=config),
    )


@dataclass(slots=True)
class Prediction:
    """Ответ одного прогона: по оси — список (значение, уверенность)."""

    labels: dict[str, list[tuple[str, float]]] = field(default_factory=dict)
    latency_s: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached: bool = False


def prediction_from_labels(labels: list[ProposedLabel]) -> dict[str, list[tuple[str, float]]]:
    grouped: dict[str, list[tuple[str, float]]] = {}
    for label in labels:
        grouped.setdefault(label.facet, []).append((label.value, float(label.confidence)))
    return grouped


def run_regex(request: ClassifyRequest, regex_module: ModuleType) -> Prediction:
    started = time.perf_counter()
    labels = regex_module.classify(request)
    return Prediction(
        labels=prediction_from_labels(labels),
        latency_s=time.perf_counter() - started,
        cached=True,
    )


def _cache_key(payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


async def run_ai(request: ClassifyRequest, ai_module: ModuleType, cache_dir: Path) -> Prediction:
    """LLM с кэшем ответов: тот же промпт второй раз денег не стоит."""

    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    payload = ai_module.build_payload(request)
    path = cache_dir / f"{_cache_key(payload)}.json"

    if path.exists():
        stored = json.loads(path.read_text(encoding="utf-8"))
        body, latency, cached = stored["body"], float(stored.get("latency_s", 0.0)), True
    else:
        started = time.perf_counter()
        body = await ai_module.call_openrouter(payload)
        latency = time.perf_counter() - started
        path.write_text(
            json.dumps({"body": body, "latency_s": latency}, ensure_ascii=False),
            encoding="utf-8",
        )
        cached = False

    usage = body.get("usage") or {}
    labels = ai_module.parse_response(request, body)
    return Prediction(
        labels=prediction_from_labels(labels),
        latency_s=latency,
        prompt_tokens=int(usage.get("prompt_tokens") or 0),
        completion_tokens=int(usage.get("completion_tokens") or 0),
        cached=cached,
    )


def combine(
    regex: Prediction,
    ai: Prediction,
    taxonomy: Taxonomy,
    regex_threshold: float = 0.6,
    ai_threshold: float = 0.6,
) -> Prediction:
    """Упрощённая копия `app.labels.recompute_effective` для двух классификаторов.

    Мнения ниже порога отбрасываются; по каждой оси побеждает ярус с большим
    приоритетом целиком (regex 200 > ai 100); для single-оси — одно лучшее.
    """

    merged: dict[str, list[tuple[str, float]]] = {}
    for facet in taxonomy.facets:
        tiers = [
            (
                REGEX_PRIORITY,
                [(v, c) for v, c in regex.labels.get(facet.slug, []) if c >= regex_threshold],
            ),
            (
                AI_PRIORITY,
                [(v, c) for v, c in ai.labels.get(facet.slug, []) if c >= ai_threshold],
            ),
        ]
        tiers.sort(key=lambda item: item[0], reverse=True)
        winners = next((labels for _priority, labels in tiers if labels), [])
        if not winners:
            continue
        winners = sorted(winners, key=lambda item: item[1], reverse=True)
        if facet.type.value == "single":
            winners = winners[:1]
        merged[facet.slug] = winners
    return Prediction(
        labels=merged,
        latency_s=regex.latency_s + ai.latency_s,
        prompt_tokens=ai.prompt_tokens,
        completion_tokens=ai.completion_tokens,
        cached=regex.cached and ai.cached,
    )
