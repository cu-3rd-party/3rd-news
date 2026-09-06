from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file="/run/config/classifier.env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
        case_sensitive=False,
        validate_default=True,
    )

    project_name: str = Field(default="3rd-news regex classifier", alias="PROJECT_NAME")
    debug: bool = Field(default=False, alias="DEBUG")
    logging_level: str = Field(default="INFO", alias="LOGGING_LEVEL")
    host: str = Field(default="0.0.0.0", alias="HOST")
    port: int = Field(default=8000, alias="PORT", ge=1, le=65535)
    classifier_node_id: str = Field(default="classifier-regex", alias="CLASSIFIER_NODE_ID")
    classifier_caller_public_key: str | None = Field(
        default=None, alias="CLASSIFIER_CALLER_PUBLIC_KEY", repr=False
    )
    classifier_expected_issuer: str = Field(default="thirdnews", alias="CLASSIFIER_EXPECTED_ISSUER")
    classifier_audience: str = Field(default="thirdnews-classifier", alias="CLASSIFIER_AUDIENCE")
    classifier_private_key: str | None = Field(
        default=None, alias="CLASSIFIER_PRIVATE_KEY", repr=False
    )
    classifier_issuer: str | None = Field(default=None, alias="CLASSIFIER_ISSUER")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
