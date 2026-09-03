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
    path = ROOT / "services" / service / "app" / "main.py"
    spec = importlib.util.spec_from_file_location(alias, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[alias] = module
    spec.loader.exec_module(module)
    return module


regex_classifier = load_service_module("classifier-regex", "classifier_regex_app")
ai_classifier = load_service_module("classifier-ai", "classifier_ai_app")
