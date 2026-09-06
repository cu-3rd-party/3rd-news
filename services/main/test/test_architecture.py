import ast
from pathlib import Path

SERVICE = Path(__file__).resolve().parents[1]
ROOT = SERVICE.parents[1]


def imports(path: Path) -> set[str]:
    result: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            result.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            result.add(node.module)
    return result


def test_domain_has_no_infrastructure_dependencies() -> None:
    forbidden = {"fastapi", "sqlalchemy", "aiohttp", "nats", "aioboto3", "pydantic_settings"}
    for path in (SERVICE / "lib/domain").rglob("*.py"):
        for dependency in imports(path):
            assert dependency.split(".")[0] not in forbidden, (path, dependency)
            assert not dependency.startswith(("lib.infra", "lib.handlers"))


def test_runtime_does_not_import_httpx_or_external_implementations() -> None:
    for path in (SERVICE / "lib").rglob("*.py"):
        for dependency in imports(path):
            assert dependency.split(".")[0] not in {"httpx", "httpx2"}, (path, dependency)
            assert not dependency.startswith(("parsers.", "classifier_ai", "classifier_regex"))


def test_handlers_do_not_depend_on_sqlalchemy_or_orm_models() -> None:
    for path in (SERVICE / "lib/handlers").rglob("*.py"):
        for dependency in imports(path):
            assert dependency.split(".")[0] != "sqlalchemy", (path, dependency)
            assert not dependency.startswith("lib.infra.storage.postgres.models"), (
                path,
                dependency,
            )


def test_shared_contracts_do_not_import_core_service() -> None:
    for path in (ROOT / "packages/python/contracts/thirdnews_contracts").rglob("*.py"):
        assert not any(name == "lib" or name.startswith("lib.") for name in imports(path))
