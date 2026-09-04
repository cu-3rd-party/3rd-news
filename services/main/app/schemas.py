"""Request/response models that are internal to this service.

Anything a parser, a classifier or a reader depends on lives in
`thirdnews_contracts` instead — that package is the public surface.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field
from thirdnews_contracts import IngestResult, NewsSubmission


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --------------------------------------------------------------------------- #
# Ingest
# --------------------------------------------------------------------------- #


class BatchSubmission(BaseModel):
    items: list[NewsSubmission] = Field(min_length=1, max_length=200)


class BatchIngestResponse(BaseModel):
    results: list[IngestResult]


# --------------------------------------------------------------------------- #
# Auth
# --------------------------------------------------------------------------- #


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class MeResponse(BaseModel):
    kind: str
    subject: str
    display_name: str
    scopes: list[str]
    role: str | None = None


# --------------------------------------------------------------------------- #
# Taxonomy admin
# --------------------------------------------------------------------------- #


class FacetValueIn(BaseModel):
    slug: str | None = None
    title: str
    description: str | None = None
    ai_hint: str | None = None
    synonyms: list[str] = Field(default_factory=list)
    match_patterns: list[str] = Field(default_factory=list)
    is_active: bool = True
    position: int = 0


class FacetValueOut(ORMModel):
    id: str
    slug: str
    title: str
    description: str | None = None
    ai_hint: str | None = None
    synonyms: list[str] = Field(default_factory=list)
    match_patterns: list[str] = Field(default_factory=list)
    is_active: bool
    position: int


class FacetIn(BaseModel):
    slug: str | None = None
    title: str
    description: str | None = None
    ai_hint: str | None = None
    type: str = "single"
    required: bool = False
    is_active: bool = True
    position: int = 0


class FacetOut(ORMModel):
    id: str
    slug: str
    title: str
    description: str | None = None
    ai_hint: str | None = None
    type: str
    required: bool
    is_active: bool
    position: int
    values: list[FacetValueOut] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Sources, keys, classifiers
# --------------------------------------------------------------------------- #


class SourceIn(BaseModel):
    slug: str | None = None
    title: str
    kind: str = "other"
    url: str | None = None
    description: str | None = None
    is_active: bool = True
    default_labels: dict[str, list[str]] = Field(default_factory=dict)
    skip_classification: bool = False


class SourceOut(ORMModel):
    id: str
    slug: str
    title: str
    kind: str
    url: str | None = None
    description: str | None = None
    is_active: bool
    default_labels: dict = Field(default_factory=dict)
    skip_classification: bool
    last_ingest_at: datetime | None = None


class ApiKeyIn(BaseModel):
    name: str
    scopes: list[str] = Field(default_factory=lambda: ["read"])
    source_id: str | None = None
    filter_preset: dict = Field(default_factory=dict)
    expires_at: datetime | None = None


class ApiKeyOut(ORMModel):
    id: str
    name: str
    prefix: str
    scopes: list[str]
    source_id: str | None = None
    filter_preset: dict = Field(default_factory=dict)
    is_active: bool
    expires_at: datetime | None = None
    last_used_at: datetime | None = None
    created_at: datetime


class ApiKeyCreated(BaseModel):
    key: ApiKeyOut
    #: Shown exactly once; the service only stores its hash.
    secret: str


class ClassifierIn(BaseModel):
    slug: str | None = None
    name: str
    base_url: str
    secret: str | None = None
    facets: list[str] = Field(default_factory=list)
    config: dict = Field(default_factory=dict)
    is_active: bool = True
    priority: int = 100
    min_confidence: float = 0.5
    auto_apply: bool = True
    timeout_s: float = 30.0


class ClassifierOut(ORMModel):
    id: str
    slug: str
    name: str
    base_url: str
    facets: list[str]
    config: dict
    is_active: bool
    priority: int
    min_confidence: float
    auto_apply: bool
    timeout_s: float
    last_ok_at: datetime | None = None
    last_error: str | None = None
    last_error_at: datetime | None = None
    #: True when a shared secret is configured; the value itself is never sent.
    has_secret: bool = False


class ClassifierProbe(BaseModel):
    ok: bool
    manifest: dict | None = None
    error: str | None = None


# --------------------------------------------------------------------------- #
# News admin
# --------------------------------------------------------------------------- #


class LabelOpinion(BaseModel):
    facet: str
    value: str
    origin: str
    origin_key: str = ""
    confidence: float = 1.0
    reason: str | None = None
    created_at: datetime | None = None


class NewsAdminDetail(BaseModel):
    """Everything an editor needs on the review screen."""

    id: str
    title: str | None
    body_md: str
    source_key: str | None
    source_link: str | None
    source_text: str | None
    published_at: datetime | None
    received_at: datetime
    status: str
    lang: str | None
    extra: dict
    manual_facets: list[str]
    classified_at: datetime | None
    attachments: list[dict]
    effective: dict[str, list[str]]
    opinions: list[LabelOpinion]


class ManualLabelsIn(BaseModel):
    """Editor's decision for one or more facets.

    A facet listed with an empty list means "deliberately no value", and is
    remembered as such so classifiers cannot fill it back in.
    """

    labels: dict[str, list[str]]
    #: Facets to hand back to the classifiers.
    release_facets: list[str] = Field(default_factory=list)


class NewsStatusIn(BaseModel):
    status: str


class NewsEditIn(BaseModel):
    title: str | None = None
    body_md: str | None = None
    source_link: str | None = None
    source_text: str | None = None
    published_at: datetime | None = None
    lang: str | None = None


class UserIn(BaseModel):
    email: EmailStr
    full_name: str | None = None
    password: str | None = None
    role: str = "editor"
    is_active: bool = True


class UserOut(ORMModel):
    id: str
    email: str
    full_name: str | None = None
    role: str
    is_active: bool
    last_login_at: datetime | None = None
    created_at: datetime


class ContextIn(BaseModel):
    """Свободный текст про организацию для классификаторов."""

    text: str = Field(max_length=20000)


class ContextOut(BaseModel):
    text: str
    #: Сколько ручных разметок реально нашлось на роль примеров.
    example_count: int
    #: Сколько запрошено настройкой NEWS_CLASSIFIER_EXAMPLE_COUNT.
    examples_configured: int


class StatsOut(BaseModel):
    news_total: int
    by_status: dict[str, int]
    pending_jobs: int
    sources: int
    classifiers_active: int
