from __future__ import annotations

import ast
import re
from pathlib import Path

from lib.infra.storage.postgres.base import Base

ROOT = Path(__file__).resolve().parents[3]
REQUIRED_LIB_DIRS = {"core", "domain", "dto", "interactor", "infra", "handlers"}


def python_imports(path: Path) -> set[str]:
    result: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            result.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            result.add(node.module)
    return result


def test_every_service_uses_the_v2_layout() -> None:
    errors: list[str] = []
    for service in sorted((ROOT / "services").iterdir()):
        if not service.is_dir():
            continue
        for required_file in ("main.py", "Dockerfile", "pyproject.toml", "uv.lock"):
            if not (service / required_file).is_file():
                errors.append(f"{service.name}: missing {required_file}")
        if not (service / "test").is_dir():
            errors.append(f"{service.name}: missing singular test directory")
        missing = REQUIRED_LIB_DIRS - {path.name for path in (service / "lib").iterdir()}
        if missing:
            errors.append(f"{service.name}: missing lib directories {sorted(missing)}")
        for legacy in ("app", "src", "tests", "requirements.txt"):
            if (service / legacy).exists():
                errors.append(f"{service.name}: replaced legacy path remains: {legacy}")
    assert not errors, "\n".join(errors)


def test_no_forbidden_http_client_or_sync_asgi_client_remains() -> None:
    forbidden_imports = {"http" + "x", "http" + "x2"}
    forbidden_symbol = "Test" + "Client"
    offenders: list[str] = []
    for path in ROOT.rglob("*.py"):
        if any(part in {".git", ".venv", "__pycache__", ".ruff_cache"} for part in path.parts):
            continue
        imports = python_imports(path)
        if any(name.split(".")[0] in forbidden_imports for name in imports):
            offenders.append(str(path.relative_to(ROOT)))
        elif forbidden_symbol in path.read_text(encoding="utf-8"):
            offenders.append(str(path.relative_to(ROOT)))
    for name in ("requirements.txt", "pyproject.toml"):
        for path in ROOT.rglob(name):
            if ".venv" in path.parts:
                continue
            lowered = path.read_text(encoding="utf-8").lower()
            if any(dependency in lowered for dependency in forbidden_imports):
                offenders.append(str(path.relative_to(ROOT)))
    assert not offenders, f"forbidden HTTP clients remain: {sorted(set(offenders))}"


def test_initial_migration_covers_every_current_model_table() -> None:
    migration_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (ROOT / "services/main/alembic/versions").glob("*.py")
    )
    migrated = set(re.findall(r"op\.create_table\(\s*['\"]([^'\"]+)", migration_text))
    assert set(Base.metadata.tables) == migrated
