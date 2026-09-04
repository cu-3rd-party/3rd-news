"""Test helpers.

Every service names its package `app` — which is right for a container that
holds exactly one service, and awkward for a test run that imports three. The
main service is a real package (it uses relative imports), so it goes on
`sys.path`; the two classifiers are single modules and are loaded by file path
under unique names.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]


def load_service_module(service: str, alias: str) -> ModuleType:
    """Загружает одиночный `app/main.py` под уникальным именем."""

    path = ROOT / "services" / service / "app" / "main.py"
    spec = importlib.util.spec_from_file_location(alias, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[alias] = module
    spec.loader.exec_module(module)
    return module


def load_package_module(base: Path, alias: str, submodule: str = "main") -> ModuleType:
    """То же, но для сервиса, чей `app` — настоящий пакет.

    Парсер TiMe разложен на `client.py` и `main.py` и пользуется
    относительными импортами, поэтому его недостаточно загрузить одним
    файлом: сначала регистрируется сам пакет с его `__path__`, и только
    потом модуль внутри него.
    """

    package_path = base / "app"
    if alias not in sys.modules:
        spec = importlib.util.spec_from_file_location(
            alias,
            package_path / "__init__.py",
            submodule_search_locations=[str(package_path)],
        )
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot load package {package_path}")
        package = importlib.util.module_from_spec(spec)
        # Регистрируем до exec_module: относительные импорты внутри пакета
        # ищут родителя именно в sys.modules.
        sys.modules[alias] = package
        spec.loader.exec_module(package)

    name = f"{alias}.{submodule}"
    if name in sys.modules:
        return sys.modules[name]
    sub_spec = importlib.util.spec_from_file_location(name, package_path / f"{submodule}.py")
    if sub_spec is None or sub_spec.loader is None:
        raise ImportError(f"cannot load {package_path / submodule}.py")
    module = importlib.util.module_from_spec(sub_spec)
    sys.modules[name] = module
    sub_spec.loader.exec_module(module)
    return module


regex_classifier = load_service_module("classifier-regex", "classifier_regex_app")
ai_classifier = load_service_module("classifier-ai", "classifier_ai_app")
time_parser = load_package_module(ROOT / "parsers" / "time", "time_parser_app")
time_client = sys.modules["time_parser_app.client"]
time_state = load_package_module(ROOT / "parsers" / "time", "time_parser_app", "state")
