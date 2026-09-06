from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file="/run/config/parser.env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
        case_sensitive=False,
        validate_default=True,
    )

    project_name: str = Field(default="3rd-news TiMe parser", alias="PROJECT_NAME")
    debug: bool = Field(default=False, alias="DEBUG")
    logging_level: str = Field(default="INFO", alias="LOGGING_LEVEL")
    host: str = Field(default="0.0.0.0", alias="HOST")
    port: int = Field(default=8000, alias="PORT", ge=1, le=65535)
    news_scheme: Literal["http", "https"] = Field(default="http", alias="NEWS_SCHEME")
    news_host: str = Field(default="api", alias="NEWS_HOST")
    news_port: int = Field(default=8000, alias="NEWS_PORT", ge=1, le=65535)
    news_api_key: SecretStr = Field(default=SecretStr(""), alias="NEWS_API_KEY")
    time_scheme: Literal["http", "https"] = Field(default="https", alias="TIME_SCHEME")
    time_host: str = Field(default="time.cu.ru", alias="TIME_HOST")
    time_port: int = Field(default=443, alias="TIME_PORT", ge=1, le=65535)
    time_cookie: SecretStr = Field(default=SecretStr(""), alias="TIME_COOKIE")
    time_csrf: SecretStr = Field(default=SecretStr(""), alias="TIME_CSRF")
    time_token: SecretStr = Field(default=SecretStr(""), alias="TIME_TOKEN")
    time_channels: str = Field(default="", alias="TIME_CHANNELS")
    poll_interval_s: int = Field(default=600, alias="POLL_INTERVAL_S", ge=1)
    max_age_days: int = Field(default=30, alias="MAX_AGE_DAYS", ge=0)
    time_posts_per_page: int = Field(default=60, alias="TIME_POSTS_PER_PAGE", ge=1, le=200)
    time_max_pages: int = Field(default=5, alias="TIME_MAX_PAGES", ge=1, le=100)
    time_include_replies: bool = Field(default=False, alias="TIME_INCLUDE_REPLIES")
    time_authors: Literal["privileged", "all"] = Field(default="privileged", alias="TIME_AUTHORS")
    time_download_attachments: bool = Field(default=True, alias="TIME_DOWNLOAD_ATTACHMENTS")
    time_max_attachment_bytes: int = Field(
        default=64 * 1024 * 1024, alias="TIME_MAX_ATTACHMENT_BYTES", ge=1024
    )
    state_path: Path = Field(default=Path("/data/state.json"), alias="STATE_PATH")
    parser_api_token: SecretStr = Field(default=SecretStr(""), alias="PARSER_API_TOKEN")
    channel_cache_ttl_s: int = Field(default=300, alias="CHANNEL_CACHE_TTL_S", ge=1)
    active_within_days: int = Field(default=90, alias="ACTIVE_WITHIN_DAYS", ge=1)

    @property
    def news_url(self) -> str:
        return f"{self.news_scheme}://{self.news_host}:{self.news_port}"

    @property
    def time_base_url(self) -> str:
        default_port = 443 if self.time_scheme == "https" else 80
        suffix = "" if self.time_port == default_port else f":{self.time_port}"
        return f"{self.time_scheme}://{self.time_host}{suffix}"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
