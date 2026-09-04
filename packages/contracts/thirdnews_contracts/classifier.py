"""The classifier protocol.

A classification service is any HTTP server that implements two endpoints:

    GET  /manifest  -> ClassifierManifest
    POST /classify  -> ClassifyResponse  (or 202 + later callback)

It is registered in the admin with its base URL and a shared secret; every
request from the main service is HMAC-signed (see `signing.py`).

Slow classifiers (LLMs) may answer `202 Accepted` with an empty body and later
POST a `CallbackResult` to `{main}/api/v1/classification/callback`, signed with
the same secret.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from .taxonomy import Taxonomy


class ClassifierManifest(BaseModel):
    slug: str
    name: str
    version: str = "0.1.0"
    contract_version: str = "1.0"
    #: Facet slugs this service can label, or `["*"]` for "whatever you send".
    facets: list[str] = Field(default_factory=lambda: ["*"])
    #: True when the service may answer 202 and call back later.
    supports_async: bool = False
    description: str | None = None


class ClassifyAttachment(BaseModel):
    kind: str
    url: str | None = None
    mime: str | None = None
    filename: str | None = None
    caption: str | None = None


class ClassifyNews(BaseModel):
    id: str
    title: str | None = None
    body_md: str
    source_link: str | None = None
    source_text: str | None = None
    published_at: datetime | None = None
    received_at: datetime | None = None
    lang: str | None = None
    attachments: list[ClassifyAttachment] = Field(default_factory=list)
    extra: dict = Field(default_factory=dict)


class ClassifyOptions(BaseModel):
    #: Restrict the answer to these facets. Empty = every facet in the taxonomy.
    facets: list[str] = Field(default_factory=list)
    #: Labels below this confidence are dropped by the main service anyway.
    min_confidence: float = 0.0
    #: Per-registration settings from the admin (model name, prompt, ...).
    config: dict = Field(default_factory=dict)
    #: Where to POST the result if the service answers 202.
    callback_url: str | None = None


class LabeledExample(BaseModel):
    """Новость, размеченная человеком — образец правильной разметки.

    Это память системы: редактор поправил метку в админке, и его решение
    уезжает следующим классификаторам как пример. Чем дольше работает
    сервис, тем лучше примеры.
    """

    title: str | None = None
    body_md: str
    #: `{"facet-slug": ["value-slug", ...]}` — так разметил человек.
    labels: dict[str, list[str]] = Field(default_factory=dict)


class ClassifyRequest(BaseModel):
    request_id: str
    news: ClassifyNews
    taxonomy: Taxonomy
    options: ClassifyOptions = Field(default_factory=ClassifyOptions)
    #: Что нужно знать об организации, чтобы вообще понимать эти тексты:
    #: расшифровки сокращений, названия потоков, кто такие кураторы. Пишется
    #: один раз в админке и приходит в каждом запросе.
    context: str | None = None
    #: Примеры ручной разметки. Необязательны: классификатор вправе их
    #: игнорировать, но с ними он попадает в принятые у вас соглашения.
    examples: list[LabeledExample] = Field(default_factory=list)


class ProposedLabel(BaseModel):
    facet: str
    value: str
    confidence: float = 1.0
    #: Short human-readable justification, kept for the admin UI.
    reason: str | None = None


class ClassifyResponse(BaseModel):
    request_id: str
    classifier: str
    labels: list[ProposedLabel] = Field(default_factory=list)
    #: Facets the service deliberately did not answer for.
    skipped: list[str] = Field(default_factory=list)
    meta: dict = Field(default_factory=dict)


class CallbackResult(BaseModel):
    """Body of the delayed answer posted back by an async classifier."""

    request_id: str
    classifier: str
    labels: list[ProposedLabel] = Field(default_factory=list)
    skipped: list[str] = Field(default_factory=list)
    error: str | None = None
    meta: dict = Field(default_factory=dict)
