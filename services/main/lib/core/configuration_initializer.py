import json
import secrets
import shlex
import shutil
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ConfigurationInitializer(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "/run/config/initializer.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
        case_sensitive=False,
        validate_default=True,
    )

    config_root: Path = Path("/config")
    runtime_uid: int = Field(default=10001, ge=0)
    runtime_gid: int = Field(default=10001, ge=0)
    environment: str = "development"
    db_scheme: str = "postgresql+asyncpg"
    db_host: str = "db"
    db_port: int = Field(default=5432, ge=1, le=65535)
    db_name: str = "news"
    db_user: str = "news"
    broker_scheme: str = "nats"
    broker_host: str = "broker"
    broker_port: int = Field(default=4222, ge=1, le=65535)
    search_scheme: str = "http"
    search_host: str = "search"
    search_port: int = Field(default=7700, ge=1, le=65535)
    file_scheme: str = "http"
    file_host: str = "file"
    file_port: int = Field(default=3900, ge=1, le=65535)
    file_bucket: str = "news"
    file_region: str = "garage"
    public_api_scheme: str = "http"
    public_api_host: str = "api"
    public_api_port: int = Field(default=8000, ge=1, le=65535)
    file_public_scheme: str = "http"
    file_public_host: str = "localhost"
    file_public_port: int = Field(default=8081, ge=1, le=65535)
    classifier_specs: list[dict[str, Any]] = Field(default_factory=list)

    def initialize(self) -> None:
        core_directory = self.config_root / "core"
        core_directory.mkdir(parents=True, exist_ok=True)
        state_path = core_directory / "bootstrap.json"
        state = self.load_or_create_state(state_path)
        node_keys = state.setdefault("node_keys", {})
        for spec in self.classifier_specs:
            node_id = str(spec["node_id"])
            if node_id not in node_keys:
                node_keys[node_id] = self.key_pair()
        self.write_json(state_path, state)
        classifiers = self.write_classifier_configuration(state)
        self.write_core_configuration(state, classifiers)
        self.write_database_configuration(state)
        self.write_search_configuration(state)
        self.write_broker_configuration(state)
        self.write_file_configuration(state)
        self.write_file(core_directory / "initialized", "")

    def load_or_create_state(self, path: Path) -> dict[str, Any]:
        if path.exists():
            value = json.loads(path.read_text())
            if not isinstance(value, dict):
                raise ValueError("bootstrap state must be an object")
            return value
        pair = self.key_pair()
        return {
            "db_password": secrets.token_urlsafe(32),
            "search_key": secrets.token_urlsafe(32),
            "broker_token": secrets.token_urlsafe(32),
            "file_access_key": f"GK{secrets.token_hex(16)}",
            "file_secret_key": secrets.token_hex(32),
            "file_rpc_secret": secrets.token_hex(32),
            "file_admin_token": secrets.token_urlsafe(32),
            "admin_password": secrets.token_urlsafe(24),
            "audit_key": Fernet.generate_key().decode(),
            "private_key": pair["private_key"],
            "public_key": pair["public_key"],
            "node_keys": {},
        }

    def write_core_configuration(
        self, state: dict[str, Any], classifiers: list[dict[str, Any]]
    ) -> None:
        nodes = [str(spec["node_id"]) for spec in self.classifier_specs]
        self.write_env(
            self.config_root / "core" / "core.env",
            {
                "ENVIRONMENT": self.environment,
                "DB_SCHEME": self.db_scheme,
                "DB_HOST": self.db_host,
                "DB_PORT": str(self.db_port),
                "DB_NAME": self.db_name,
                "DB_USER": self.db_user,
                "DB_PASSWORD": str(state["db_password"]),
                "BROKER_SCHEME": self.broker_scheme,
                "BROKER_HOST": self.broker_host,
                "BROKER_PORT": str(self.broker_port),
                "BROKER_TOKEN": str(state["broker_token"]),
                "SEARCH_SCHEME": self.search_scheme,
                "SEARCH_HOST": self.search_host,
                "SEARCH_PORT": str(self.search_port),
                "SEARCH_KEY": str(state["search_key"]),
                "FILE_SCHEME": self.file_scheme,
                "FILE_HOST": self.file_host,
                "FILE_PORT": str(self.file_port),
                "FILE_PUBLIC_SCHEME": self.file_public_scheme,
                "FILE_PUBLIC_HOST": self.file_public_host,
                "FILE_PUBLIC_PORT": str(self.file_public_port),
                "FILE_BUCKET": self.file_bucket,
                "FILE_REGION": self.file_region,
                "FILE_ACCESS_KEY": str(state["file_access_key"]),
                "FILE_SECRET_KEY": str(state["file_secret_key"]),
                "PUBLIC_API_SCHEME": self.public_api_scheme,
                "PUBLIC_API_HOST": self.public_api_host,
                "PUBLIC_API_PORT": str(self.public_api_port),
                "AUTH_PRIVATE_KEY": str(state["private_key"]),
                "AUTH_PUBLIC_KEY": str(state["public_key"]),
                "RAW_AUDIT_ENCRYPTION_KEY": str(state["audit_key"]),
                "CLASSIFIER_SERVICE_HOSTS": json.dumps(nodes),
                "CLASSIFIER_REQUEST_TIMEOUT_SECONDS": "180",
                "WORKER_LEASE_SECONDS": "240",
                "BOOTSTRAP_ADMIN_EMAIL": "admin@example.edu",
                "BOOTSTRAP_ADMIN_PASSWORD": str(state["admin_password"]),
                "BOOTSTRAP_CLASSIFIERS": json.dumps(classifiers),
            },
        )

    def write_classifier_configuration(self, state: dict[str, Any]) -> list[dict[str, Any]]:
        result = []
        for spec in self.classifier_specs:
            node_id = str(spec["node_id"])
            pair = state["node_keys"][node_id]
            self.write_env(
                self.config_root / node_id / "classifier.env",
                {
                    "CLASSIFIER_NODE_ID": node_id,
                    "CLASSIFIER_ISSUER": node_id,
                    "CLASSIFIER_PRIVATE_KEY": str(pair["private_key"]),
                    "CLASSIFIER_CALLER_PUBLIC_KEY": str(state["public_key"]),
                    "CLASSIFIER_EXPECTED_ISSUER": "thirdnews",
                    "CLASSIFIER_AUDIENCE": "thirdnews-classifier",
                },
            )
            classifier = {key: value for key, value in spec.items() if key != "node_id"}
            classifier["signing_public_key"] = str(pair["public_key"])
            result.append(classifier)
        return result

    def write_database_configuration(self, state: dict[str, Any]) -> None:
        self.write_env(
            self.config_root / "db" / "db.env",
            {
                "POSTGRES_USER": self.db_user,
                "POSTGRES_DB": self.db_name,
                "POSTGRES_PASSWORD": str(state["db_password"]),
            },
        )

    def write_search_configuration(self, state: dict[str, Any]) -> None:
        self.write_env(
            self.config_root / "search" / "search.env",
            {"MEILI_MASTER_KEY": str(state["search_key"])},
        )

    def write_broker_configuration(self, state: dict[str, Any]) -> None:
        self.write_file(
            self.config_root / "broker" / "nats.conf",
            "\n".join(
                (
                    f"port: {self.broker_port}",
                    "http_port: 8222",
                    f'authorization {{ token: "{state["broker_token"]}" }}',
                    'jetstream { store_dir: "/data", max_file_store: 1GB, max_memory_store: 64MB }',
                    "max_payload: 65536",
                    "",
                )
            ),
        )

    def write_file_configuration(self, state: dict[str, Any]) -> None:
        self.write_env(
            self.config_root / "file" / "file.env",
            {
                "GARAGE_DEFAULT_ACCESS_KEY": str(state["file_access_key"]),
                "GARAGE_DEFAULT_SECRET_KEY": str(state["file_secret_key"]),
                "GARAGE_DEFAULT_BUCKET": self.file_bucket,
            },
        )
        self.write_file(
            self.config_root / "file" / "garage.toml",
            "\n".join(
                (
                    'metadata_dir = "/data/meta"',
                    'data_dir = "/data/objects"',
                    'db_engine = "sqlite"',
                    "replication_factor = 1",
                    'rpc_bind_addr = "[::]:3901"',
                    f'rpc_public_addr = "{self.file_host}:3901"',
                    f'rpc_secret = "{state["file_rpc_secret"]}"',
                    "[s3_api]",
                    f's3_region = "{self.file_region}"',
                    f'api_bind_addr = "[::]:{self.file_port}"',
                    "[admin]",
                    'api_bind_addr = "[::]:3903"',
                    f'admin_token = "{state["file_admin_token"]}"',
                    "",
                )
            ),
        )

    def write_env(self, path: Path, values: dict[str, str]) -> None:
        self.write_file(
            path, "".join(f"{key}={shlex.quote(value)}\n" for key, value in values.items())
        )

    def write_json(self, path: Path, value: dict[str, Any]) -> None:
        self.write_file(path, json.dumps(value))

    def write_file(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{secrets.token_hex(8)}.tmp")
        temporary.write_text(content)
        temporary.chmod(0o600)
        shutil.chown(temporary, user=self.runtime_uid, group=self.runtime_gid)
        temporary.replace(path)

    @staticmethod
    def key_pair() -> dict[str, str]:
        key = Ed25519PrivateKey.generate()
        return {
            "private_key": key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            ).decode(),
            "public_key": key.public_key()
            .public_bytes(
                serialization.Encoding.PEM,
                serialization.PublicFormat.SubjectPublicKeyInfo,
            )
            .decode(),
        }
