from functools import lru_cache
from typing import Literal
from urllib.parse import quote

from pydantic import Field, SecretStr, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class TestSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "/run/config/core.env"),
        extra="ignore",
        populate_by_name=True,
        case_sensitive=False,
    )

    db_scheme: Literal["postgresql+asyncpg"] = Field(
        default="postgresql+asyncpg", alias="TEST_DB_SCHEME"
    )
    db_host: str = Field(default="", alias="TEST_DB_HOST")
    db_port: int = Field(default=5432, alias="TEST_DB_PORT", ge=1, le=65535)
    db_name: str = Field(default="news", alias="TEST_DB_NAME")
    db_user: str = Field(default="news", alias="TEST_DB_USER")
    db_password: SecretStr = Field(default=SecretStr(""), alias="TEST_DB_PASSWORD")

    @property
    def configured(self) -> bool:
        return bool(self.db_host and self.db_password.get_secret_value())

    @computed_field(repr=False)
    @property
    def database_url(self) -> str:
        user = quote(self.db_user, safe="")
        password = quote(self.db_password.get_secret_value(), safe="")
        name = quote(self.db_name, safe="")
        return f"{self.db_scheme}://{user}:{password}@{self.db_host}:{self.db_port}/{name}"


@lru_cache
def get_test_settings() -> TestSettings:
    return TestSettings()
