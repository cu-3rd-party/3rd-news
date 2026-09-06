import uuid
from typing import Literal

from pydantic import Field, SecretStr, computed_field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class LoadSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "/run/config/core.env"),
        extra="ignore",
        populate_by_name=True,
        case_sensitive=False,
    )

    api_scheme: Literal["http", "https"] = Field(default="http", alias="LOAD_API_SCHEME")
    api_host: str = Field(default="127.0.0.1", alias="LOAD_API_HOST")
    api_port: int = Field(default=8080, alias="LOAD_API_PORT", ge=1, le=65535)
    count: int = Field(default=20, alias="LOAD_COUNT", ge=20, le=40)
    concurrency: int = Field(default=10, alias="LOAD_CONCURRENCY", ge=1)
    mode: Literal["full", "queue"] = Field(default="full", alias="LOAD_MODE")
    run_id: str = Field(default_factory=lambda: f"load-{uuid.uuid4().hex}", alias="LOAD_RUN_ID")
    worker_replicas: int | None = Field(default=None, alias="LOAD_WORKER_REPLICAS", ge=1)
    timeout_seconds: float = Field(default=600, alias="LOAD_TIMEOUT_SECONDS", gt=0)
    poll_seconds: float = Field(default=0.5, alias="LOAD_POLL_SECONDS", gt=0)
    negative_checks: bool = Field(default=False, alias="LOAD_NEGATIVE_CHECKS")
    allow_duplicates: bool = Field(default=False, alias="LOAD_ALLOW_DUPLICATES")
    admin_email: str = Field(default="admin@example.edu", alias="LOAD_ADMIN_EMAIL")
    admin_password: SecretStr = Field(default=SecretStr(""), alias="LOAD_ADMIN_PASSWORD")
    access_token: SecretStr = Field(default=SecretStr(""), alias="LOAD_TOKEN")
    bootstrap_admin_email: str = Field(default="", alias="BOOTSTRAP_ADMIN_EMAIL")
    bootstrap_admin_password: SecretStr = Field(
        default=SecretStr(""), alias="BOOTSTRAP_ADMIN_PASSWORD"
    )

    @computed_field
    @property
    def base_url(self) -> str:
        return f"{self.api_scheme}://{self.api_host}:{self.api_port}"

    @model_validator(mode="after")
    def validate_concurrency(self) -> LoadSettings:
        if self.concurrency > self.count:
            raise ValueError("LOAD_CONCURRENCY must not exceed LOAD_COUNT")
        return self

    @property
    def token_value(self) -> str:
        return self.access_token.get_secret_value()

    @property
    def email_value(self) -> str:
        return self.admin_email or self.bootstrap_admin_email

    @property
    def password_value(self) -> str:
        return (
            self.admin_password.get_secret_value()
            or self.bootstrap_admin_password.get_secret_value()
        )
