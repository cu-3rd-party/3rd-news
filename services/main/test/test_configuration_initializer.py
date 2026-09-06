import json
from pathlib import Path

from lib.core.config import Settings
from lib.core.configuration_initializer import ConfigurationInitializer


def test_initializer_is_atomic_and_preserves_first_run_credentials(tmp_path: Path) -> None:
    stat = tmp_path.stat()
    specs = [
        {
            "node_id": "classifier-test",
            "slug": "test",
            "name": "Test",
            "endpoint": "http://classifier-test:8000",
            "allowed_axes": [],
            "enabled": True,
            "shadow": False,
            "priority": 1,
            "min_confidence": 0.5,
            "timeout_seconds": 30,
        }
    ]
    initializer = ConfigurationInitializer(
        config_root=tmp_path,
        runtime_uid=stat.st_uid,
        runtime_gid=stat.st_gid,
        classifier_specs=specs,
    )
    initializer.initialize()
    state_before = json.loads((tmp_path / "core" / "bootstrap.json").read_text())
    initializer.initialize()
    state_after = json.loads((tmp_path / "core" / "bootstrap.json").read_text())
    core = (tmp_path / "core" / "core.env").read_text()

    assert state_after == state_before
    assert "DB_HOST=db\n" in core
    assert "BROKER_HOST=broker\n" in core
    assert "SEARCH_HOST=search\n" in core
    assert "FILE_HOST=file\n" in core
    assert "DB_URL=" not in core
    assert "BROKER_URL=" not in core
    assert "SEARCH_URL=" not in core
    assert "FILE_ENDPOINT=" not in core
    assert list(tmp_path.rglob("*.tmp")) == []


def test_settings_construct_encoded_urls_from_atomic_fields() -> None:
    settings = Settings(
        db_user="news user",
        db_password="p@ss/word",
        broker_token="t@ken",
        search_scheme="https",
        search_host="search.example.edu",
        search_port=443,
    )

    assert settings.db_url == ("postgresql+asyncpg://news%20user:p%40ss%2Fword@localhost:5432/news")
    assert settings.broker_url == "nats://t%40ken@localhost:4222"
    assert settings.search_url == "https://search.example.edu:443"
