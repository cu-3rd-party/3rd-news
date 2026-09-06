from __future__ import annotations

from pathlib import Path
from typing import Any

from ...domain.entities.patch import Patch
from ...domain.entities.plan import Plan
from ..interfaces.clients.http import HttpClient

TAXONOMY_PATH = Path(__file__).resolve().parents[2] / "infra" / "storage" / "taxonomy.json"
FACET_FIELDS = ("title", "ai_hint", "type", "position")
VALUE_FIELDS = ("title", "ai_hint", "synonyms", "match_patterns", "position")
FACET_PATCH_FIELDS = (
    "slug",
    "title",
    "description",
    "ai_hint",
    "type",
    "required",
    "is_active",
    "position",
)
VALUE_PATCH_FIELDS = (
    "slug",
    "title",
    "description",
    "ai_hint",
    "synonyms",
    "match_patterns",
    "is_active",
    "position",
)
SOURCE_PATCH_FIELDS = (
    "slug",
    "title",
    "kind",
    "url",
    "description",
    "is_active",
    "default_labels",
    "skip_classification",
)


def _diff(
    existing: dict[str, Any], desired: dict[str, Any], fields: tuple[str, ...]
) -> dict[str, Any]:
    changed: dict[str, Any] = {}
    for name in fields:
        if name not in desired:
            continue
        if existing.get(name) != desired[name]:
            changed[name] = desired[name]
    return changed


def _payload(existing: dict[str, Any], fields: tuple[str, ...], **changes: Any) -> dict[str, Any]:
    payload = {name: existing[name] for name in fields if existing.get(name) is not None}
    payload.update(changes)
    return payload


def plan_changes(existing: list[dict[str, Any]], desired: list[dict[str, Any]]) -> Plan:
    by_slug = {facet["slug"]: facet for facet in existing}
    plan = Plan()
    for spec in desired:
        current = by_slug.get(spec["slug"])
        if current is None:
            plan.create_facets.append(spec)
            continue
        changed = _diff(current, spec, FACET_FIELDS)
        if changed:
            plan.patch_facets.append(
                Patch(
                    current["id"],
                    spec["slug"],
                    changed,
                    _payload(current, FACET_PATCH_FIELDS, **changed),
                )
            )
        values_by_slug = {value["slug"]: value for value in current.get("values", [])}
        wanted_values = {value["slug"] for value in spec.get("values", [])}
        for position, value_spec in enumerate(spec.get("values", [])):
            value_spec = {**value_spec, "position": position}
            value = values_by_slug.get(value_spec["slug"])
            if value is None:
                plan.create_values.append((current["id"], spec["slug"], value_spec))
                continue
            value_changed = _diff(value, value_spec, VALUE_FIELDS)
            if value_changed:
                plan.patch_values.append(
                    Patch(
                        value["id"],
                        f"{spec['slug']}.{value_spec['slug']}",
                        value_changed,
                        _payload(value, VALUE_PATCH_FIELDS, **value_changed),
                    )
                )
        for slug, value in values_by_slug.items():
            if slug not in wanted_values and value.get("is_active", True):
                plan.deactivate_values.append(
                    Patch(
                        value["id"],
                        f"{spec['slug']}.{slug}",
                        {"is_active": False},
                        _payload(value, VALUE_PATCH_FIELDS, is_active=False),
                    )
                )
    wanted = {spec["slug"] for spec in desired}
    for slug, facet in by_slug.items():
        if slug not in wanted and facet.get("is_active", True):
            plan.deactivate_facets.append(
                Patch(
                    facet["id"],
                    slug,
                    {"is_active": False},
                    _payload(facet, FACET_PATCH_FIELDS, is_active=False),
                )
            )
    return plan


def source_defaults(desired: list[dict[str, Any]]) -> dict[str, dict[str, list[str]]]:
    wanted: dict[str, dict[str, list[str]]] = {}
    for spec in desired:
        for value in spec.get("values", []):
            for source_key in value.get("source_keys", []):
                facet_values = wanted.setdefault(source_key, {}).setdefault(spec["slug"], [])
                if value["slug"] not in facet_values:
                    facet_values.append(value["slug"])
    return wanted


def plan_sources(
    existing: list[dict[str, Any]], wanted: dict[str, dict[str, list[str]]]
) -> tuple[list[Patch], list[str]]:
    by_slug = {source["slug"]: source for source in existing}
    patches: list[Patch] = []
    missing: list[str] = []
    for source_key, facets in sorted(wanted.items()):
        source = by_slug.get(source_key)
        if source is None:
            missing.append(source_key)
            continue
        labels = dict(source.get("default_labels") or {})
        if all((sorted(labels.get(slug, [])) == sorted(values) for slug, values in facets.items())):
            continue
        labels.update(facets)
        patches.append(
            Patch(
                source["id"],
                source_key,
                {"default_labels": labels},
                _payload(source, SOURCE_PATCH_FIELDS, default_labels=labels),
            )
        )
    return (patches, missing)


def describe(plan: Plan, deactivate: bool = False) -> str:
    lines: list[str] = []
    for spec in plan.create_facets:
        lines.append(
            f"+ ось {spec['slug']} ({spec['title']}), значений: {len(spec.get('values', []))}"
        )
    for patch in plan.patch_facets:
        lines.append(f"~ ось {patch.label}: {', '.join(sorted(patch.changed))}")
    for _, slug, spec in plan.create_values:
        lines.append(f"+ значение {slug}.{spec['slug']} ({spec['title']})")
    for patch in plan.patch_values:
        lines.append(f"~ значение {patch.label}: {', '.join(sorted(patch.changed))}")
    for patch in plan.patch_sources:
        labels = patch.changed["default_labels"]
        shown = ", ".join(
            (f"{facet}={'+'.join(values)}" for facet, values in sorted(labels.items()))
        )
        lines.append(f"~ источник {patch.label}: default_labels {shown}")
    verb = "выключаю" if deactivate else "нет в файле, не трогаю"
    for patch in plan.deactivate_facets:
        lines.append(f"- ось {patch.label}: {verb}")
    for patch in plan.deactivate_values:
        lines.append(f"- значение {patch.label}: {verb}")
    for source_key in plan.missing_sources:
        lines.append(f"? источника {source_key} нет в админке (парсер ещё не приносил новостей)")
    if not deactivate and (plan.deactivate_facets or plan.deactivate_values):
        lines.append("  (--deactivate-extra выключит их, не удаляя)")
    return "\n".join(lines) or "изменений нет"


def _token(client: HttpClient, email: str, password: str) -> str:
    response = client.post("/api/v1/auth/token", json={"email": email, "password": password})
    response.raise_for_status()
    return response.json()["access_token"]


def _facet_wire(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "slug": payload["slug"],
        "title": payload["title"],
        "description": payload.get("description"),
        "ai_hint": payload.get("ai_hint"),
        "kind": payload.get("type", "single"),
        "required": payload.get("required", False),
        "enabled": payload.get("is_active", True),
        "position": payload.get("position", 0),
    }


def _value_wire(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "slug": payload["slug"],
        "title": payload["title"],
        "description": payload.get("description"),
        "ai_hint": payload.get("ai_hint"),
        "synonyms": payload.get("synonyms", []),
        "match_patterns": payload.get("match_patterns", []),
        "enabled": payload.get("is_active", True),
        "position": payload.get("position", 0),
    }


def _source_wire(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "slug": payload["slug"],
        "title": payload["title"],
        "kind": payload.get("kind", "other"),
        "url": payload.get("url"),
        "description": payload.get("description"),
        "enabled": payload.get("is_active", True),
        "skip_classification": payload.get("skip_classification", False),
        "default_labels": payload.get("default_labels", {}),
    }


def _normalize_facets(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            **item,
            "type": item.get("kind", "single"),
            "is_active": item.get("enabled", True),
            "values": [
                {**value, "is_active": value.get("enabled", True)}
                for value in item.get("values", [])
            ],
        }
        for item in items
    ]


def _normalize_sources(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{**item, "is_active": item.get("enabled", True)} for item in items]


def apply(client: HttpClient, plan: Plan, deactivate: bool = False) -> None:
    for spec in plan.create_facets:
        payload = {name: spec[name] for name in FACET_FIELDS if name in spec}
        payload["slug"] = spec["slug"]
        payload["position"] = spec.get("position", 0)
        response = client.post("/api/v1/admin/facets", json=_facet_wire(payload))
        response.raise_for_status()
        facet_id = response.json()["id"]
        for position, value_spec in enumerate(spec.get("values", [])):
            _create_value(client, facet_id, value_spec, position)
    for facet_id, _, value_spec in plan.create_values:
        _create_value(client, facet_id, value_spec, value_spec.get("position", 0))
    for patch in plan.patch_facets:
        client.patch(
            f"/api/v1/admin/facets/{patch.id}", json=_facet_wire(patch.payload)
        ).raise_for_status()
    for patch in plan.patch_values:
        client.patch(
            f"/api/v1/admin/facet-values/{patch.id}", json=_value_wire(patch.payload)
        ).raise_for_status()
    if deactivate:
        for patch in plan.deactivate_values:
            client.patch(
                f"/api/v1/admin/facet-values/{patch.id}", json=_value_wire(patch.payload)
            ).raise_for_status()
        for patch in plan.deactivate_facets:
            client.patch(
                f"/api/v1/admin/facets/{patch.id}", json=_facet_wire(patch.payload)
            ).raise_for_status()
    for patch in plan.patch_sources:
        client.patch(
            f"/api/v1/admin/sources/{patch.id}", json=_source_wire(patch.payload)
        ).raise_for_status()


def _create_value(client: HttpClient, facet_id: str, spec: dict[str, Any], position: int) -> None:
    payload = {name: spec[name] for name in VALUE_FIELDS if name in spec}
    payload["slug"] = spec["slug"]
    payload["position"] = position
    client.post(
        f"/api/v1/admin/facets/{facet_id}/values", json=_value_wire(payload)
    ).raise_for_status()
