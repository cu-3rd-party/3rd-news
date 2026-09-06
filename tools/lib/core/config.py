from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
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

    main_scheme: Literal["http", "https"] = Field(default="http", alias="MAIN_SCHEME")
    main_host: str = Field(default="127.0.0.1", alias="MAIN_HOST")
    main_port: int = Field(default=8000, alias="MAIN_PORT", ge=1, le=65535)
    admin_email: str = Field(default="", alias="BOOTSTRAP_ADMIN_EMAIL")
    admin_password: SecretStr = Field(default=SecretStr(""), alias="BOOTSTRAP_ADMIN_PASSWORD")
    eval_action: Literal["run", "compare", "blind", "kappa"] = Field(
        default="run", alias="EVAL_ACTION"
    )
    eval_data_path: Path = Field(default=Path("data/gold.jsonl"), alias="EVAL_DATA_PATH")
    eval_taxonomy_path: Path = Field(
        default=Path("tools/lib/infra/storage/taxonomy.json"), alias="EVAL_TAXONOMY_PATH"
    )
    eval_context_path: Path | None = Field(default=None, alias="EVAL_CONTEXT_PATH")
    eval_output_path: Path = Field(default=Path("data/eval.json"), alias="EVAL_OUTPUT_PATH")
    eval_result_paths: list[Path] = Field(default_factory=list, alias="EVAL_RESULT_PATHS")
    eval_other_path: Path | None = Field(default=None, alias="EVAL_OTHER_PATH")
    eval_classifier: Literal["regex", "ai", "combined"] = Field(
        default="regex", alias="EVAL_CLASSIFIER"
    )
    eval_examples: Literal["none", "recent", "knn"] = Field(default="none", alias="EVAL_EXAMPLES")
    eval_k: int = Field(default=8, alias="EVAL_K", ge=0)
    eval_model: str | None = Field(default=None, alias="EVAL_MODEL")
    eval_min_confidence: float = Field(default=0.0, alias="EVAL_MIN_CONFIDENCE", ge=0, le=1)
    eval_regex_threshold: float = Field(default=0.6, alias="EVAL_REGEX_THRESHOLD", ge=0, le=1)
    eval_ai_threshold: float = Field(default=0.6, alias="EVAL_AI_THRESHOLD", ge=0, le=1)
    eval_embedder: Literal["e5", "fake"] = Field(default="e5", alias="EVAL_EMBEDDER")
    eval_embedding_model: str = Field(
        default="intfloat/multilingual-e5-base", alias="EVAL_EMBEDDING_MODEL"
    )
    eval_cache_path: Path = Field(default=Path("data/cache"), alias="EVAL_CACHE_PATH")
    eval_only_gold: bool = Field(default=False, alias="EVAL_ONLY_GOLD")
    eval_sample_size: int = Field(default=100, alias="EVAL_SAMPLE_SIZE", ge=1)
    eval_seed: int = Field(default=1, alias="EVAL_SEED")
    eval_show: int = Field(default=20, alias="EVAL_SHOW", ge=0)
    corpus_action: Literal[
        "copy-labels",
        "duplicates",
        "gold",
        "progress",
        "reject-noise",
        "release-facet",
        "sample",
    ] = Field(default="progress", alias="CORPUS_ACTION")
    corpus_apply: bool = Field(default=False, alias="CORPUS_APPLY")
    corpus_threshold: float = Field(default=0.8, alias="CORPUS_THRESHOLD", ge=0, le=1)
    corpus_size: int = Field(default=200, alias="CORPUS_SIZE", ge=1)
    corpus_cap: float = Field(default=0.2, alias="CORPUS_CAP", gt=0, le=1)
    corpus_seed: int = Field(default=1, alias="CORPUS_SEED")
    corpus_by_channel: bool = Field(default=False, alias="CORPUS_BY_CHANNEL")
    corpus_fresh: bool = Field(default=False, alias="CORPUS_FRESH")
    corpus_gold_copies: bool = Field(default=False, alias="CORPUS_GOLD_COPIES")
    corpus_clear_gold: bool = Field(default=False, alias="CORPUS_CLEAR_GOLD")
    corpus_status: str = Field(default="published", alias="CORPUS_STATUS")
    corpus_facet: str = Field(default="program", alias="CORPUS_FACET")
    corpus_output_path: Path | None = Field(default=None, alias="CORPUS_OUTPUT_PATH")
    corpus_input_path: Path = Field(default=Path("data/raw.jsonl"), alias="CORPUS_INPUT_PATH")
    taxonomy_path: Path = Field(
        default=Path("tools/lib/infra/storage/taxonomy.json"), alias="TAXONOMY_PATH"
    )
    taxonomy_deactivate_extra: bool = Field(default=False, alias="TAXONOMY_DEACTIVATE_EXTRA")
    taxonomy_dry_run: bool = Field(default=True, alias="TAXONOMY_DRY_RUN")

    @property
    def main_url(self) -> str:
        return f"{self.main_scheme}://{self.main_host}:{self.main_port}"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
