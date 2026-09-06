from typing import Literal

from pydantic import Field, SecretStr, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ComposeSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "/run/config/core.env"),
        extra="ignore",
        populate_by_name=True,
        case_sensitive=False,
    )

    api_scheme: Literal["http", "https"] = Field(default="http", alias="COMPOSE_API_SCHEME")
    api_host: str = Field(default="127.0.0.1", alias="COMPOSE_API_HOST")
    api_port: int = Field(default=8080, alias="COMPOSE_API_PORT", ge=1, le=65535)
    admin_email: str = Field(default="admin@example.edu", alias="COMPOSE_ADMIN_EMAIL")
    admin_password: SecretStr = Field(default=SecretStr(""), alias="COMPOSE_ADMIN_PASSWORD")

    @computed_field
    @property
    def base_url(self) -> str:
        return f"{self.api_scheme}://{self.api_host}:{self.api_port}"

    @property
    def password_value(self) -> str:
        return self.admin_password.get_secret_value()
