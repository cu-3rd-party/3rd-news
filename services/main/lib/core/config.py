import base64
import ipaddress
from datetime import timedelta
from functools import lru_cache
from socket import gethostname
from typing import Literal
from urllib.parse import quote, urlsplit
from zipfile import ZIP_DEFLATED, ZIP_STORED

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

OUTBOX_RETRY_DELAY_MAX_SECONDS = 900
OUTBOX_RETRY_EXPONENT_MAX = 10
OUTBOX_ATTEMPT_COUNTER_MAX = 2_000_000_000
UPLOAD_PENDING_MAX_COUNT = 20
UPLOAD_PENDING_MAX_BYTES = 200_000_000
UPLOAD_UNUSED_RETENTION_DAYS = 7
OBJECT_GC_GRACE_HOURS = 24
OBJECT_GC_INTERVAL_SECONDS = 300
OBJECT_GC_BATCH_SIZE = 100

SEARCH_BATCH_MAX_BYTES = 8_000_000
SEARCH_FILTERABLE = (
    "status",
    "facets",
    "visibility_revision",
    "source",
    "source_ids",
    "language",
    "has_attachments",
    "published_at_ts",
    "received_at_ts",
    "importance",
    "urgency",
    "impact",
    "editorial_priority",
)
SEARCH_SORTABLE = (
    "published_at",
    "published_at_ts",
    "received_at_ts",
    "importance",
    "urgency",
    "impact",
    "editorial_priority",
)
TEXT_ATTACHMENT_TYPES = frozenset(
    {
        "application/json",
        "application/xml",
        "text/csv",
        "text/html",
        "text/markdown",
        "text/plain",
        "text/xml",
    }
)
DOCX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
DOCX_XML_MAX_BYTES = 8 * 1024 * 1024
DOCX_COMPRESSION_RATIO_MAX = 200
DOCX_READ_CHUNK_BYTES = 64 * 1024
DOCX_COMPRESSION_METHODS = frozenset({ZIP_STORED, ZIP_DEFLATED})
HTML_IGNORED_ELEMENTS = frozenset({"script", "style", "template", "svg"})
PDF_STREAM_MAX_BYTES = 16 * 1024 * 1024
PDF_PAGE_MAX_COUNT = 1_000
PDF_BOUNDED_FILTER_ATTRIBUTES = (
    "MAX_DECLARED_STREAM_LENGTH",
    "MAX_ARRAY_BASED_STREAM_OUTPUT_LENGTH",
    "JBIG2_MAX_OUTPUT_LENGTH",
    "LZW_MAX_OUTPUT_LENGTH",
    "RUN_LENGTH_MAX_OUTPUT_LENGTH",
    "ZLIB_MAX_OUTPUT_LENGTH",
    "FLATE_MAX_BUFFER_SIZE",
)
TEXT_EXTRACTION_INPUT_MAX_BYTES = 50_000_000
TEXT_EXTRACTION_CHARACTER_MAX = 1_000_000
TEXT_EXTRACTION_OUTPUT_MAX_BYTES_PER_CHARACTER = 4
TEXT_EXTRACTION_ERROR_MAX_BYTES = 64 * 1024
TEXT_EXTRACTION_IO_CHUNK_BYTES = 64 * 1024
TEXT_EXTRACTION_HEADER_MAX_BYTES = 8 * 1024
TEXT_EXTRACTION_TIMEOUT_SECONDS = 10.0
TEXT_EXTRACTION_MEMORY_MAX_BYTES = 384 * 1024 * 1024
TEXT_EXTRACTION_CPU_MAX_SECONDS = 5
REMATERIALIZATION_JOB_KIND = "rematerialize"
REMATERIALIZATION_BATCH_SIZE = 50
TAXONOMY_REVISION_LOCK_ID = 8_424_917_321
CLASSIFIER_EXAMPLE_DEFAULT_COUNT = 20
CLASSIFIER_EXAMPLE_MAX_COUNT = 50
CLASSIFIER_EXAMPLE_BODY_MAX_CHARACTERS = 8_000
DATABASE_NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}
AUTH_DUMMY_PASSWORD_HASH = (
    "$argon2id$v=19$m=65536,t=3,p=4$F7Hl5IpHAN1T6uENCiRpMA$"
    "81gm7/lz4wrDha6/gP0fGoRwwYrDu9i/yG+dq3QQMy8"
)
AUTH_SESSION_COOKIE = "thirdnews_session"
AUTH_CSRF_COOKIE = "thirdnews_csrf"
AUTH_SESSION_TTL = timedelta(hours=8)
AUTH_TOKEN_TTL = timedelta(minutes=15)
AUTH_ROLE_SCOPES = {
    "admin": frozenset({"read", "ingest", "editor", "admin", "raw_audit"}),
    "editor": frozenset({"read", "editor"}),
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="",
        extra="ignore",
        case_sensitive=False,
        populate_by_name=True,
        validate_default=True,
        env_file=(".env", "/run/config/core.env"),
        env_file_encoding="utf-8",
    )

    project_name: str = "3rd-news"
    environment: Literal["development", "testing", "production"] = "development"
    service_mode: Literal[
        "api",
        "initialize",
        "migrate",
        "worker-outbox",
        "worker-pipeline",
        "worker-index",
    ] = "api"
    db_scheme: Literal["postgresql+asyncpg"] = "postgresql+asyncpg"
    db_host: str = "localhost"
    db_port: int = Field(default=5432, ge=1, le=65535)
    db_name: str = "news"
    db_user: str = "news"
    db_password: SecretStr = Field(default=SecretStr("news"), repr=False)
    broker_scheme: Literal["nats", "tls"] = "nats"
    broker_host: str = "localhost"
    broker_port: int = Field(default=4222, ge=1, le=65535)
    broker_token: SecretStr = Field(default=SecretStr(""), repr=False)
    broker_stream: str = "THIRDNEWS"
    broker_subject_prefix: str = "thirdnews.v2"
    broker_connect_timeout: float = 5.0
    search_scheme: Literal["http", "https"] = "http"
    search_host: str = "localhost"
    search_port: int = Field(default=7700, ge=1, le=65535)
    search_key: SecretStr = Field(default=SecretStr(""), repr=False)
    search_index: str = "news-v2"
    search_task_timeout_seconds: float = 30.0
    file_scheme: Literal["http", "https"] = "http"
    file_host: str = "localhost"
    file_port: int = Field(default=3900, ge=1, le=65535)
    file_public_scheme: Literal["http", "https"] = "http"
    file_public_host: str = "localhost"
    file_public_port: int = Field(default=3900, ge=1, le=65535)
    file_bucket: str = "news"
    file_region: str = "garage"
    file_access_key: SecretStr = Field(default=SecretStr(""), repr=False)
    file_secret_key: SecretStr = Field(default=SecretStr(""), repr=False)
    file_presign_ttl_seconds: int = Field(default=900, ge=60, le=3600)
    upload_max_bytes: int = Field(default=50_000_000, ge=1)
    request_max_bytes: int = Field(default=8_000_000, ge=1024, le=100_000_000)
    public_api_scheme: Literal["http", "https"] = "http"
    public_api_host: str = "localhost"
    public_api_port: int = Field(default=8080, ge=1, le=65535)
    auth_private_key: str = Field(default="", repr=False)
    auth_public_key: str = Field(default="", repr=False)
    auth_password_verify_concurrency: int = Field(default=2, ge=1, le=32)
    auth_password_verify_queue_size: int = Field(default=16, ge=0, le=1_000)
    auth_trusted_proxy_hosts: list[str] = Field(default_factory=lambda: ["proxy"])
    auth_login_attempt_limit: int = Field(default=5, ge=1, le=100)
    auth_login_window_seconds: int = Field(default=900, ge=1, le=86_400)
    auth_login_base_cooldown_seconds: int = Field(default=2, ge=1, le=3_600)
    auth_login_max_cooldown_seconds: int = Field(default=900, ge=1, le=86_400)
    auth_api_key_touch_interval_seconds: int = Field(default=300, ge=1, le=86_400)
    bootstrap_admin_email: str = "admin@example.edu"
    bootstrap_admin_password: str = Field(default="", repr=False)
    bootstrap_classifiers: list[dict[str, object]] = Field(default_factory=list, repr=False)
    api_host: str = "0.0.0.0"
    api_port: int = Field(default=8000, ge=1, le=65535)
    api_workers: int = Field(default=1, ge=1)
    api_healthcheck_host: str = "127.0.0.1"
    debug: bool = False
    logging_level: str = "INFO"
    healthcheck_timeout_seconds: float = Field(default=3, gt=0)
    pipeline_cooldown_seconds: int = Field(default=5, ge=0)
    max_attempts: int = Field(default=5, ge=1)
    callback_timeout_seconds: int = Field(default=300, ge=1)
    worker_node_id: str = Field(default_factory=gethostname)
    worker_batch_size: int = Field(default=20, ge=1, le=200)
    worker_concurrency: int = Field(default=4, ge=1)
    worker_lease_seconds: int = Field(default=120, ge=1)
    worker_poll_seconds: float = Field(default=0.5, gt=0)
    classifier_request_timeout_seconds: float = 30.0
    classifier_response_max_bytes: int = Field(default=1_000_000, ge=1, le=10_000_000)
    classifier_issuer: str = "thirdnews"
    classifier_audience: str = "thirdnews-classifier"
    callback_audience: str = "thirdnews-api"
    ssrf_allow_hosts: list[str] = Field(default_factory=list)
    classifier_service_hosts: list[str] = Field(default_factory=list)
    fetch_max_redirects: int = Field(default=3, ge=0, le=10)
    fetch_timeout_seconds: float = 15.0
    fetch_max_bytes: int = Field(default=10_000_000, ge=1)
    raw_audit_retention_days: int = Field(default=30, ge=1)
    raw_audit_encryption_key: str = Field(default="", repr=False)

    @field_validator("logging_level")
    @classmethod
    def normalize_logging_level(cls, value: str) -> str:
        level = value.upper()
        if level not in {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET"}:
            raise ValueError("invalid logging level")
        return level

    @property
    def db_url(self) -> str:
        user = quote(self.db_user, safe="")
        password = quote(self.db_password.get_secret_value(), safe="")
        name = quote(self.db_name, safe="")
        return f"{self.db_scheme}://{user}:{password}@{self.db_host}:{self.db_port}/{name}"

    @property
    def broker_url(self) -> str:
        token = quote(self.broker_token.get_secret_value(), safe="")
        credentials = f"{token}@" if token else ""
        return f"{self.broker_scheme}://{credentials}{self.broker_host}:{self.broker_port}"

    @property
    def search_url(self) -> str:
        return f"{self.search_scheme}://{self.search_host}:{self.search_port}"

    @property
    def search_key_value(self) -> str:
        return self.search_key.get_secret_value()

    @property
    def file_endpoint(self) -> str:
        return f"{self.file_scheme}://{self.file_host}:{self.file_port}"

    @property
    def file_public_endpoint(self) -> str:
        return f"{self.file_public_scheme}://{self.file_public_host}:{self.file_public_port}"

    @property
    def file_access_key_value(self) -> str:
        return self.file_access_key.get_secret_value()

    @property
    def file_secret_key_value(self) -> str:
        return self.file_secret_key.get_secret_value()

    @property
    def public_base_url(self) -> str:
        return f"{self.public_api_scheme}://{self.public_api_host}:{self.public_api_port}"

    @model_validator(mode="after")
    def validate_production_boundaries(self) -> Settings:
        if self.environment != "production":
            return self
        endpoint = urlsplit(self.file_public_endpoint)
        host = endpoint.hostname or ""
        if (
            endpoint.scheme != "https"
            or not host
            or endpoint.username
            or endpoint.password
            or endpoint.query
            or endpoint.fragment
            or endpoint.path not in ("", "/")
        ):
            raise ValueError("production FILE_PUBLIC_ENDPOINT must be a public HTTPS origin")
        if host == "localhost" or host.endswith((".localhost", ".local")):
            raise ValueError("production FILE_PUBLIC_ENDPOINT cannot be local")
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            address = None
        if address is not None and not address.is_global:
            raise ValueError("production FILE_PUBLIC_ENDPOINT cannot be private")
        try:
            key = base64.b64decode(self.raw_audit_encryption_key, altchars=b"-_", validate=True)
        except ValueError:
            key = b""
        if len(key) != 32 or len(set(key)) < 8:
            raise ValueError("production requires a random 32-byte base64 raw audit key")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
