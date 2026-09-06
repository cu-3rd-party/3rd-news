import json

from ..core.config import Settings, get_settings
from ..infra.clients.tool_http import ToolHttpClient
from ..interactor.use_cases.apply_taxonomy import (
    _normalize_facets,
    _normalize_sources,
    _token,
    apply,
    describe,
    plan_changes,
    plan_sources,
    source_defaults,
)


def run(settings: Settings) -> int:
    email = settings.admin_email
    password = settings.admin_password.get_secret_value()
    if not email or not password:
        raise RuntimeError("administrator credentials are required")
    desired = json.loads(settings.taxonomy_path.read_text(encoding="utf-8"))["facets"]
    with ToolHttpClient(settings.main_url, timeout=30.0) as client:
        client.headers["Authorization"] = f"Bearer {_token(client, email, password)}"
        facets = client.get("/api/v1/admin/facets")
        facets.raise_for_status()
        plan = plan_changes(_normalize_facets(facets.json()["items"]), desired)
        sources = client.get("/api/v1/admin/sources")
        sources.raise_for_status()
        plan.patch_sources, plan.missing_sources = plan_sources(
            _normalize_sources(sources.json()["items"]), source_defaults(desired)
        )
        print(describe(plan, settings.taxonomy_deactivate_extra))
        if settings.taxonomy_dry_run or not plan.has_work(settings.taxonomy_deactivate_extra):
            return 0
        apply(client, plan, settings.taxonomy_deactivate_extra)
    return 0


def main() -> int:
    return run(get_settings())
