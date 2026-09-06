from functools import lru_cache
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

    project_name: str = Field(default="3rd-news RSS parser", alias="PROJECT_NAME")
    debug: bool = Field(default=False, alias="DEBUG")
    logging_level: str = Field(default="INFO", alias="LOGGING_LEVEL")
    host: str = Field(default="0.0.0.0", alias="HOST")
    port: int = Field(default=8000, alias="PORT", ge=1, le=65535)
    news_scheme: Literal["http", "https"] = Field(default="http", alias="NEWS_SCHEME")
    news_host: str = Field(default="api", alias="NEWS_HOST")
    news_port: int = Field(default=8000, alias="NEWS_PORT", ge=1, le=65535)
    news_api_key: SecretStr = Field(default=SecretStr(""), alias="NEWS_API_KEY")
    feeds: str = Field(default="", alias="FEEDS")
    poll_interval_s: int = Field(default=600, alias="POLL_INTERVAL_S", ge=1)
    retry_delay_s: float = Field(default=5.0, alias="RETRY_DELAY_S", ge=0, le=300)
    max_age_days: int = Field(default=30, alias="MAX_AGE_DAYS", ge=0)
    max_feed_bytes: int = Field(default=8 * 1024 * 1024, alias="MAX_FEED_BYTES", ge=1024)
    fetch_timeout_s: float = Field(default=30, alias="FETCH_TIMEOUT_S", gt=0, le=300)

    @property
    def news_url(self) -> str:
        return f"{self.news_scheme}://{self.news_host}:{self.news_port}"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
