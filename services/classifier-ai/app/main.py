"""LLM classifier backed by OpenRouter.

The prompt is built from the taxonomy in the request, so this service never
knows what "importance" or "поток" mean — the admin's titles, descriptions and
`ai_hint` fields are the whole specification. Per-registration overrides
(model, temperature, extra instructions) arrive in `options.config`.
"""

from __future__ import annotations

import json
import logging
import os
import re

import httpx
from thirdnews_contracts import ClassifyRequest, ProposedLabel
from thirdnews_contracts.worker import build_classifier_app

logger = logging.getLogger("3rdnews.classifier.ai")

SLUG = "openrouter"
SECRET = os.getenv("CLASSIFIER_SECRET") or None
API_KEY = os.getenv("OPENROUTER_API_KEY", "")
API_URL = os.getenv("OPENROUTER_URL", "https://openrouter.ai/api/v1/chat/completions")
DEFAULT_MODEL = os.getenv("OPENROUTER_MODEL", "anthropic/claude-haiku-4.5")
#: Long posts are truncated: the first characters carry the topic, and tokens
#: cost money.
MAX_BODY_CHARS = int(os.getenv("MAX_BODY_CHARS", "6000"))
REQUEST_TIMEOUT = float(os.getenv("REQUEST_TIMEOUT", "60"))
#: Ответ — короткий JSON, но рассуждающим моделям нужен запас, иначе они
#: упираются в лимит посреди размышлений и не доходят до самого ответа.
MAX_OUTPUT_TOKENS = int(os.getenv("MAX_OUTPUT_TOKENS", "2000"))

SYSTEM_PROMPT = """\
Ты классифицируешь новости университета по заданным осям (facets).
Отвечай ТОЛЬКО JSON-объектом вида:
{"labels": [{"facet": "<slug>", "value": "<slug>", "confidence": 0.0-1.0, "reason": "кратко"}]}

Правила:
- используй только те facet и value, которые перечислены в схеме;
- для оси с type=single выбери не больше одного значения;
- для оси с type=multi можно выбрать несколько значений;
- если для оси нет уверенного ответа, просто не включай её в labels;
- confidence — твоя реальная уверенность, не завышай её.
"""


def _taxonomy_prompt(request: ClassifyRequest) -> str:
    wanted = set(request.options.facets or [])
    lines: list[str] = []
    for facet in request.taxonomy.facets:
        if wanted and facet.slug not in wanted:
            continue
        header = f'- facet "{facet.slug}" ({facet.title}, type={facet.type.value})'
        if facet.ai_hint or facet.description:
            header += f": {facet.ai_hint or facet.description}"
        lines.append(header)
        for value in facet.values:
            hint = value.ai_hint or value.description or ""
            synonyms = ", ".join(value.synonyms[:8])
            suffix = f" — {hint}" if hint else ""
            if synonyms:
                suffix += f" (ключевые слова: {synonyms})"
            lines.append(f'    * value "{value.slug}" ({value.title}){suffix}')
    return "\n".join(lines)


def _context_prompt(request: ClassifyRequest) -> str:
    """Что редактор рассказал модели об организации.

    Без этого «ВКР», «поток Восток» и «Fundamentals» для модели просто
    незнакомые слова, и она додумывает их значение сама.
    """

    context = (request.context or "").strip()
    return f"Что нужно знать об университете:\n{context}" if context else ""


def _examples_prompt(request: ClassifyRequest) -> str:
    """Как размечает редактор — на живых примерах.

    Это память системы: правки в админке возвращаются сюда и задают принятые
    соглашения точнее любой инструкции.
    """

    if not request.examples:
        return ""

    blocks = []
    for example in request.examples:
        labels = json.dumps(example.labels, ensure_ascii=False)
        head = (example.title or example.body_md[:60]).strip()
        body = " ".join(example.body_md.split())[:400]
        blocks.append(f"— «{head}»\n  текст: {body}\n  разметка: {labels}")
    return (
        "Примеры того, как эти же оси размечал редактор. Следуй этим "
        "соглашениям, а не своим представлениям:\n" + "\n".join(blocks)
    )


def _news_prompt(request: ClassifyRequest) -> str:
    news = request.news
    body = news.body_md[:MAX_BODY_CHARS]
    if len(news.body_md) > MAX_BODY_CHARS:
        body += "\n[...текст обрезан...]"
    attachments = ", ".join(item.kind for item in news.attachments) or "нет"
    return (
        f"Заголовок: {news.title or '(нет)'}\n"
        f"Источник: {news.source_text or news.source_link or '(неизвестен)'}\n"
        f"Дата публикации: {news.published_at or '(неизвестна)'}\n"
        f"Вложения: {attachments}\n\n"
        f"Текст:\n{body}"
    )


def _content_of(body: dict, model: str) -> str:
    """Достаёт текст ответа, не веря, что он там обязательно есть.

    У рассуждающих моделей `content` бывает пустым или `null`: весь бюджет
    ушёл на размышления. Тогда JSON ищем прямо в них — модель обычно
    проговаривает ответ до того, как обрывается.
    """

    if body.get("error"):
        raise RuntimeError(f"{model}: {str(body['error'])[:300]}")

    choices = body.get("choices") or []
    if not choices:
        raise RuntimeError(f"{model} не вернул ни одного варианта ответа")

    message = choices[0].get("message") or {}
    for field in ("content", "reasoning"):
        value = message.get(field)
        if value and value.strip():
            if field == "reasoning":
                logger.info("%s оставил content пустым, разбираю reasoning", model)
            return value

    finish = choices[0].get("finish_reason")
    raise RuntimeError(
        f"{model} вернул пустой ответ (finish_reason={finish}); "
        "скорее всего не хватило max_tokens"
    )


def _extract_json(content: str) -> dict:
    """Pull the JSON object out of a reply that may be wrapped in prose."""

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", content, re.DOTALL)
    if not match:
        raise ValueError(f"model did not return JSON: {content[:200]}")
    return json.loads(match.group(0))


def _valid_labels(request: ClassifyRequest, raw: dict) -> list[ProposedLabel]:
    """Keep only labels that exist in the taxonomy we sent."""

    allowed = {
        facet.slug: {value.slug for value in facet.values} for facet in request.taxonomy.facets
    }
    single = {facet.slug for facet in request.taxonomy.facets if facet.type.value == "single"}

    labels: list[ProposedLabel] = []
    used_single: set[str] = set()
    for item in raw.get("labels", []):
        facet = str(item.get("facet", ""))
        value = str(item.get("value", ""))
        if value not in allowed.get(facet, set()):
            logger.info("model proposed unknown label %s/%s, dropping", facet, value)
            continue
        if facet in single:
            if facet in used_single:
                continue
            used_single.add(facet)
        try:
            confidence = float(item.get("confidence", 0.7))
        except (TypeError, ValueError):
            confidence = 0.7
        confidence = max(0.0, min(1.0, confidence))
        if confidence < request.options.min_confidence:
            continue
        labels.append(
            ProposedLabel(
                facet=facet,
                value=value,
                confidence=confidence,
                reason=str(item.get("reason") or "")[:500] or None,
            )
        )
    return labels


async def classify(request: ClassifyRequest) -> list[ProposedLabel]:
    if not API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY is not set")

    config = request.options.config or {}
    model = config.get("model") or DEFAULT_MODEL
    extra_instructions = config.get("instructions") or ""

    user_prompt = "\n\n".join(
        part
        for part in (
            _context_prompt(request),
            "Схема классификации:\n" + _taxonomy_prompt(request),
            _examples_prompt(request),
            extra_instructions,
            "Новость:\n" + _news_prompt(request),
        )
        if part and part.strip()
    ).strip()

    payload = {
        "model": model,
        "temperature": config.get("temperature", 0.0),
        "response_format": {"type": "json_object"},
        "max_tokens": config.get("max_tokens", MAX_OUTPUT_TOKENS),
        # Классификация по готовому рубрикатору — не та задача, где нужны
        # длинные размышления: они удваивают цену и съедают бюджет вывода,
        # после чего модель возвращает пустой content. Кому надо — включит
        # обратно через config.
        "reasoning": config.get("reasoning", {"enabled": False}),
        "messages": [
            {"role": "system", "content": config.get("system_prompt") or SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    }
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
        # OpenRouter uses these for attribution on its dashboard.
        "HTTP-Referer": os.getenv("OPENROUTER_REFERER", "https://github.com/3rd-news"),
        "X-Title": "3rd-news classifier",
    }

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as http:
        response = await http.post(API_URL, json=payload, headers=headers)
        response.raise_for_status()
        body = response.json()

    return _valid_labels(request, _extract_json(_content_of(body, model)))


app = build_classifier_app(
    slug=SLUG,
    name="OpenRouter LLM classifier",
    classify=classify,
    secret=SECRET,
    version="0.1.0",
    description="Asks an LLM through OpenRouter, constrained to the taxonomy it is given.",
)
