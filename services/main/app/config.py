from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="NEWS_", env_file=".env", extra="ignore")

    app_name: str = "3rd-news"
    environment: str = "development"
    debug: bool = False

    database_url: str = "postgresql+asyncpg://news:news@localhost:5432/news"
    redis_url: str = "redis://localhost:6379/0"

    #: Root of the media volume; attachments live under `<media_root>/<yyyy>/<mm>/`.
    media_root: Path = Path("/data/media")
    #: Public prefix the delivery API prepends to stored attachment paths.
    media_base_url: str = "/media"
    max_attachment_bytes: int = 512 * 1024 * 1024

    #: Ordered auth backends tried for the delivery endpoint.
    auth_backends: list[str] = Field(default=["api_key", "jwt", "session"])
    secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_public_key: str | None = None
    jwt_issuer: str | None = None
    jwt_audience: str | None = None
    jwt_ttl_seconds: int = 3600
    session_cookie_name: str = "news_session"
    session_ttl_seconds: int = 14 * 24 * 3600

    #: Labels proposed by a classifier below this are stored but never applied.
    default_min_confidence: float = 0.5
    classifier_timeout_s: float = 30.0
    classification_max_attempts: int = 3
    #: Publish automatically once classification finishes and every required
    #: facet has a value. Turn off to make an editor confirm each item.
    auto_publish: bool = True
    #: Delivery endpoint returns only these statuses unless a caller with the
    #: `editor` scope asks for others.
    public_statuses: list[str] = Field(default=["published"])

    cors_origins: list[str] = Field(default=["http://localhost:5173"])

    #: Created on first boot when the users table is empty.
    bootstrap_admin_email: str | None = None
    bootstrap_admin_password: str | None = None

    #: Public base URL of this service, used to build classifier callback URLs.
    public_base_url: str = "http://localhost:8000"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
