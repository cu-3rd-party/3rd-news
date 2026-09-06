from functools import lru_cache
from typing import Literal
from urllib.parse import quote

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
        case_sensitive=False,
        validate_default=True,
    )

    # ^ General
    project_name: str = Field(default="project-name", alias="PROJECT_NAME")
    debug: bool = Field(default=False, alias="DEBUG")
    logging_level: str = Field(default="INFO", alias="LOGGING_LEVEL")
    timezone: str = Field(default="UTC", alias="TIMEZONE")

    # ^ Backend
    backend_host: str = Field(default="0.0.0.0", alias="BACKEND_HOST")  # noqa: S104  # nosec B104
    backend_port: int = Field(default=8700, alias="BACKEND_PORT", ge=1, le=65535)
    backend_workers: int = Field(default=2, alias="BACKEND_WORKERS", ge=1)
    backend_api_prefix: str = Field(default="/api", alias="BACKEND_API_PREFIX")
    resources_healthcheck_timeout: float = Field(
        default=19.0,
        alias="RESOURCES_HEALTHCHECK_TIMEOUT",
        gt=0,
    )

    # ^ Granian
    granian_log_access_enabled: bool = Field(
        default=False,
        alias="GRANIAN_LOG_ACCESS_ENABLED",
    )
    granian_http: Literal["auto", "1", "2", "3"] = Field(
        default="auto",
        alias="GRANIAN_HTTP",
    )

    # ^ Database
    db_host: str = Field(default="postgres", alias="DB_HOST")
    db_port: int = Field(default=5432, alias="DB_PORT", ge=1, le=65535)
    db_name: str = Field(default="db", alias="DB_NAME")
    db_user: str = Field(default="admin", alias="DB_USER")
    db_password: SecretStr = Field(default=SecretStr("admin"), alias="DB_PASSWORD")
    db_pool_min_size: int = Field(default=1, alias="DB_POOL_MIN_SIZE", ge=0)
    db_pool_max_size: int = Field(default=10, alias="DB_POOL_MAX_SIZE", ge=1)
    db_statement_cache_size: int = Field(
        default=0,
        alias="DB_STATEMENT_CACHE_SIZE",
        ge=0,
    )
    db_command_timeout: float = Field(default=30.0, alias="DB_COMMAND_TIMEOUT", gt=0)

    # ^ Search
    search_engine_scheme: Literal["http", "https"] = Field(
        default="http",
        alias="SEARCH_ENGINE_SCHEME",
    )
    search_engine_host: str = Field(default="meilisearch", alias="SEARCH_ENGINE_HOST")
    search_engine_port: int = Field(
        default=7700,
        alias="SEARCH_ENGINE_PORT",
        ge=1,
        le=65535,
    )
    search_engine_master_key: SecretStr = Field(
        default=SecretStr("admin"),
        alias="SEARCH_ENGINE_MASTER_KEY",
    )
    search_engine_no_analytics: bool = Field(
        default=True,
        alias="SEARCH_ENGINE_NO_ANALYTICS",
    )
    search_engine_timeout: float = Field(
        default=5.0,
        alias="SEARCH_ENGINE_TIMEOUT",
        gt=0,
    )

    # ^ Cache
    cache_scheme: Literal["redis", "rediss"] = Field(
        default="redis",
        alias="CACHE_SCHEME",
    )
    cache_host: str = Field(default="dragonfly", alias="CACHE_HOST")
    cache_port: int = Field(default=6379, alias="CACHE_PORT", ge=1, le=65535)
    cache_password: SecretStr = Field(default=SecretStr("admin"), alias="CACHE_PASSWORD")
    cache_db: int = Field(default=0, alias="CACHE_DB", ge=0)
    cache_pool_max_connections: int = Field(
        default=100,
        alias="CACHE_POOL_MAX_CONNECTIONS",
        ge=1,
    )
    cache_connect_timeout: float = Field(
        default=5.0,
        alias="CACHE_CONNECT_TIMEOUT",
        gt=0,
    )
    cache_command_timeout: float = Field(
        default=5.0,
        alias="CACHE_COMMAND_TIMEOUT",
        gt=0,
    )

    # ^ Tools
    api_fuzz_url: str = Field(
        default="http://127.0.0.1:8700/api/openapi.json",
        alias="API_FUZZ_URL",
    )

    @field_validator("logging_level")
    @classmethod
    def normalize_logging_level(cls, value: str) -> str:
        level = value.upper()
        if level not in {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET"}:
            msg = "LOGGING_LEVEL must be one of CRITICAL, ERROR, WARNING, INFO, DEBUG, NOTSET"
            raise ValueError(msg)
        return level

    @property
    def database_url(self) -> str:
        user = quote(self.db_user, safe="")
        password = quote(self.db_password.get_secret_value(), safe="")
        name = quote(self.db_name, safe="")
        return f"postgresql://{user}:{password}@{self.db_host}:{self.db_port}/{name}"

    @property
    def search_engine_url(self) -> str:
        return f"{self.search_engine_scheme}://{self.search_engine_host}:{self.search_engine_port}"

    @property
    def cache_url(self) -> str:
        password = quote(self.cache_password.get_secret_value(), safe="")
        return (
            f"{self.cache_scheme}://:{password}@{self.cache_host}:{self.cache_port}/{self.cache_db}"
        )

    @property
    def search_engine_master_key_value(self) -> str:
        return self.search_engine_master_key.get_secret_value()


@lru_cache
def get_settings() -> Settings:
    return Settings()
