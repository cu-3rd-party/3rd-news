from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
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

    project_name: str = Field(default="3rd-news AI classifier", alias="PROJECT_NAME")
    debug: bool = Field(default=False, alias="DEBUG")
    logging_level: str = Field(default="INFO", alias="LOGGING_LEVEL")
    host: str = Field(default="0.0.0.0", alias="HOST")
    port: int = Field(default=8000, alias="PORT", ge=1, le=65535)
    classifier_node_id: str = Field(default="classifier-ai", alias="CLASSIFIER_NODE_ID")
    classifier_caller_public_key: str | None = Field(
        default=None, alias="CLASSIFIER_CALLER_PUBLIC_KEY", repr=False
    )
    classifier_expected_issuer: str = Field(default="thirdnews", alias="CLASSIFIER_EXPECTED_ISSUER")
    classifier_audience: str = Field(default="thirdnews-classifier", alias="CLASSIFIER_AUDIENCE")
    classifier_private_key: str | None = Field(
        default=None, alias="CLASSIFIER_PRIVATE_KEY", repr=False
    )
    classifier_issuer: str | None = Field(default=None, alias="CLASSIFIER_ISSUER")
    classifier_async_callbacks: bool = Field(default=False, alias="CLASSIFIER_ASYNC_CALLBACKS")
    provider_protocol: Literal["openai", "ollama-native"] = Field(
        default="openai", alias="PROVIDER_PROTOCOL"
    )
    openai_scheme: Literal["http", "https"] = Field(default="http", alias="OPENAI_SCHEME")
    openai_host: str = Field(default="ollama", alias="OPENAI_HOST")
    openai_port: int = Field(default=11434, alias="OPENAI_PORT", ge=1, le=65535)
    openai_path: str = Field(default="/v1", alias="OPENAI_PATH")
    ollama_scheme: Literal["http", "https"] = Field(default="http", alias="OLLAMA_SCHEME")
    ollama_host: str = Field(default="ollama", alias="OLLAMA_HOST")
    ollama_port: int = Field(default=11434, alias="OLLAMA_PORT", ge=1, le=65535)
    openai_api_key: SecretStr = Field(default=SecretStr(""), alias="OPENAI_API_KEY")
    openai_model: str = Field(default="qwen3:0.6b", alias="OPENAI_MODEL")
    openai_reasoning_effort: Literal["none", "low", "medium", "high", "max"] | None = Field(
        default=None, alias="OPENAI_REASONING_EFFORT"
    )
    openai_response_format: Literal["json_schema", "json_object"] = Field(
        default="json_schema", alias="OPENAI_RESPONSE_FORMAT"
    )
    openai_timeout_s: float = Field(default=60.0, alias="OPENAI_TIMEOUT_S", gt=0)
    max_body_chars: int = Field(default=12_000, alias="MAX_BODY_CHARS", ge=1)
    max_output_tokens: int = Field(default=2_000, alias="MAX_OUTPUT_TOKENS", ge=1)
    max_provider_response_bytes: int = Field(
        default=2 * 1024 * 1024,
        alias="MAX_PROVIDER_RESPONSE_BYTES",
        ge=1024,
        le=16 * 1024 * 1024,
    )
    ollama_num_threads: int = Field(default=2, alias="OLLAMA_NUM_THREADS", ge=1)
    ollama_num_ctx: int = Field(default=4096, alias="OLLAMA_NUM_CTX", ge=512)

    @property
    def openai_base_url(self) -> str:
        path = f"/{self.openai_path.strip('/')}" if self.openai_path.strip("/") else ""
        return f"{self.openai_scheme}://{self.openai_host}:{self.openai_port}{path}"

    @property
    def ollama_base_url(self) -> str:
        return f"{self.ollama_scheme}://{self.ollama_host}:{self.ollama_port}"

    def require_openai_key(self) -> str:
        key = self.openai_api_key.get_secret_value().strip()
        if self.provider_protocol == "openai" and key.lower() in {"", "ollama", "changeme"}:
            raise ValueError("OPENAI_API_KEY is required for the OpenAI provider")
        return key


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
