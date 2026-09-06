import importlib
import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

ROOT = Path(__file__).resolve().parents[4]


def load_service(service: str, alias: str) -> None:
    package_path = ROOT / "services" / service / "lib"
    spec = importlib.util.spec_from_file_location(
        alias,
        package_path / "__init__.py",
        submodule_search_locations=[str(package_path)],
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {package_path}")
    package = importlib.util.module_from_spec(spec)
    sys.modules[alias] = package
    try:
        spec.loader.exec_module(package)
    except Exception:
        for name in [key for key in sys.modules if key == alias or key.startswith(f"{alias}.")]:
            sys.modules.pop(name, None)
        raise


def load_classifiers() -> tuple[ModuleType, Any]:
    regex_alias = "eval_classifier_regex"
    ai_alias = "eval_classifier_ai"
    if regex_alias not in sys.modules:
        load_service("classifier-regex", regex_alias)
    if ai_alias not in sys.modules:
        load_service("classifier-ai", ai_alias)
    regex = importlib.import_module(f"{regex_alias}.interactor.use_cases.classify")
    config = importlib.import_module(f"{ai_alias}.core.config")
    payloads = importlib.import_module(f"{ai_alias}.interactor.use_cases.build_payload")
    normalize = importlib.import_module(f"{ai_alias}.interactor.use_cases.normalize_response")
    openai_module = importlib.import_module(f"{ai_alias}.infra.clients.openai")
    ollama_module = importlib.import_module(f"{ai_alias}.infra.clients.ollama")
    settings = config.get_settings()
    provider = (
        ollama_module.OllamaClient(settings)
        if settings.provider_protocol == "ollama-native"
        else openai_module.OpenAIClient(settings)
    )
    ai = SimpleNamespace(
        build_payload=lambda request: payloads.build_payload(request, settings),
        call_provider=provider.complete,
        parse_response=normalize.parse_response,
    )
    return regex, ai
