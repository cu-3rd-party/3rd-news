"""Заводит оси разметки из `taxonomy.json` в админке главного сервиса.

Идемпотентно и по умолчанию ничего не выключает: то, чего нет в файле, скрипт
показывает в конце прогона, чтобы редактор решил сам. Сравнение идёт по
`slug`, так что повторный запуск после правки файла обновляет заголовки,
`ai_hint`, синонимы и паттерны у уже заведённых осей.

С `--deactivate-extra` оси и значения, которых нет в файле, получают
`is_active: false`. Это нужно при первом применении поверх стартовой
таксономии-заглушки: она заняла slug `audience` под ось «Формат», и без
выключения старых значений разметчик увидит «внешние спикеры» внутри
«Аудитории». Выключение обратимо и не трогает уже проставленные метки —
удалять оси скрипт не умеет принципиально.

Ось `program` человеком не размечается: у её значений есть `source_keys`,
и скрипт раскладывает их в `default_labels` соответствующих источников —
направление приходит из канала, а не из текста объявления.

    python -m tools.taxonomy.apply --dry-run
    python -m tools.taxonomy.apply --deactivate-extra
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

TAXONOMY_PATH = Path(__file__).with_name("taxonomy.json")

#: Поля, которые скрипт держит в согласии с файлом. `is_active` не трогаем —
#: им управляет `--deactivate-extra`. А вот `position` синхронизируем: порядок
#: осей и значений задаёт файл, и он же определяет нумерацию клавиш в разметке,
#: так что расхождение с экраном стоит дороже свободы переставлять в админке.
FACET_FIELDS = ("title", "ai_hint", "type", "position")
VALUE_FIELDS = ("title", "ai_hint", "synonyms", "match_patterns", "position")

#: PATCH в этом API — полная замена: `update_facet` присваивает все поля тела.
#: Поэтому патч собирается из текущей записи, а не из одних изменений, иначе
#: правка `ai_hint` обнулила бы `match_patterns` и `position`.
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
#: `update_source` устроен так же: `title` обязателен, остальное перезаписывается.
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


@dataclass
class Patch:
    """Одно обновление: что показать человеку и что реально отправить."""

    id: str
    label: str
    #: Только для вывода плана.
    changed: dict[str, Any]
    #: Полное тело запроса.
    payload: dict[str, Any]


@dataclass
class Plan:
    """Что нужно сделать, чтобы админка совпала с файлом."""

    create_facets: list[dict[str, Any]] = field(default_factory=list)
    patch_facets: list[Patch] = field(default_factory=list)
    create_values: list[tuple[str, str, dict[str, Any]]] = field(default_factory=list)
    patch_values: list[Patch] = field(default_factory=list)
    patch_sources: list[Patch] = field(default_factory=list)
    missing_sources: list[str] = field(default_factory=list)
    #: Оси и значения, которых нет в файле, — выключаются только по флагу.
    deactivate_facets: list[Patch] = field(default_factory=list)
    deactivate_values: list[Patch] = field(default_factory=list)

    def has_work(self, deactivate: bool = False) -> bool:
        work = bool(
            self.create_facets
            or self.patch_facets
            or self.create_values
            or self.patch_values
            or self.patch_sources
        )
        if deactivate:
            work = work or bool(self.deactivate_facets or self.deactivate_values)
        return work


def _diff(existing: dict[str, Any], desired: dict[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
    changed: dict[str, Any] = {}
    for name in fields:
        if name not in desired:
            continue
        if existing.get(name) != desired[name]:
            changed[name] = desired[name]
    return changed


def _payload(existing: dict[str, Any], fields: tuple[str, ...], **changes: Any) -> dict[str, Any]:
    """Текущая запись целиком плюс правки — PATCH здесь заменяет объект."""

    payload = {name: existing[name] for name in fields if existing.get(name) is not None}
    payload.update(changes)
    return payload


def plan_changes(existing: list[dict[str, Any]], desired: list[dict[str, Any]]) -> Plan:
    """Чистая функция: сравнивает `GET /admin/facets` с содержимым файла."""

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
            # Позиция значения — это его место в файле, отдельного поля нет.
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
    """Каким источникам какие значения `program` проставить.

    Один канал может нести несколько значений, поэтому собираем список, а не
    перезаписываем: «оплата обучения» в семи каналах — это семь источников с
    одним значением каждый, но канал совместной программы вполне может
    относиться сразу к двум направлениям.
    """

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
    """Патчи `default_labels` и список каналов, которых в админке ещё нет.

    Чужие оси в `default_labels` не трогаем: источнику могли руками поставить
    дефолтную важность, и это не наше дело.
    """

    by_slug = {source["slug"]: source for source in existing}
    patches: list[Patch] = []
    missing: list[str] = []

    for source_key, facets in sorted(wanted.items()):
        source = by_slug.get(source_key)
        if source is None:
            missing.append(source_key)
            continue
        labels = dict(source.get("default_labels") or {})
        if all(sorted(labels.get(slug, [])) == sorted(values) for slug, values in facets.items()):
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
    return patches, missing


def describe(plan: Plan, deactivate: bool = False) -> str:
    lines: list[str] = []
    for spec in plan.create_facets:
        lines.append(f"+ ось {spec['slug']} ({spec['title']}), значений: {len(spec.get('values', []))}")
    for patch in plan.patch_facets:
        lines.append(f"~ ось {patch.label}: {', '.join(sorted(patch.changed))}")
    for _, slug, spec in plan.create_values:
        lines.append(f"+ значение {slug}.{spec['slug']} ({spec['title']})")
    for patch in plan.patch_values:
        lines.append(f"~ значение {patch.label}: {', '.join(sorted(patch.changed))}")
    for patch in plan.patch_sources:
        labels = patch.changed["default_labels"]
        shown = ", ".join(f"{facet}={'+'.join(values)}" for facet, values in sorted(labels.items()))
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


def _token(client: httpx.Client, email: str, password: str) -> str:
    response = client.post("/api/v1/auth/token", json={"email": email, "password": password})
    response.raise_for_status()
    return response.json()["access_token"]


def apply(client: httpx.Client, plan: Plan, deactivate: bool = False) -> None:
    for spec in plan.create_facets:
        payload = {name: spec[name] for name in FACET_FIELDS if name in spec}
        payload["slug"] = spec["slug"]
        payload["position"] = spec.get("position", 0)
        response = client.post("/api/v1/admin/facets", json=payload)
        response.raise_for_status()
        facet_id = response.json()["id"]
        for position, value_spec in enumerate(spec.get("values", [])):
            _create_value(client, facet_id, value_spec, position)

    for facet_id, _, value_spec in plan.create_values:
        _create_value(client, facet_id, value_spec, value_spec.get("position", 0))


    for patch in plan.patch_facets:
        client.patch(f"/api/v1/admin/facets/{patch.id}", json=patch.payload).raise_for_status()
    for patch in plan.patch_values:
        client.patch(f"/api/v1/admin/values/{patch.id}", json=patch.payload).raise_for_status()

    if deactivate:
        # Значения выключаем раньше осей: если прогон оборвётся посередине,
        # включённая ось с выключенными значениями безопаснее обратного.
        for patch in plan.deactivate_values:
            client.patch(f"/api/v1/admin/values/{patch.id}", json=patch.payload).raise_for_status()
        for patch in plan.deactivate_facets:
            client.patch(f"/api/v1/admin/facets/{patch.id}", json=patch.payload).raise_for_status()

    for patch in plan.patch_sources:
        client.patch(f"/api/v1/admin/sources/{patch.id}", json=patch.payload).raise_for_status()


def _create_value(client: httpx.Client, facet_id: str, spec: dict[str, Any], position: int) -> None:
    payload = {name: spec[name] for name in VALUE_FIELDS if name in spec}
    payload["slug"] = spec["slug"]
    payload["position"] = position
    client.post(f"/api/v1/admin/facets/{facet_id}/values", json=payload).raise_for_status()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=os.getenv("MAIN_BASE_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--email", default=os.getenv("BOOTSTRAP_ADMIN_EMAIL"))
    parser.add_argument("--password", default=os.getenv("BOOTSTRAP_ADMIN_PASSWORD"))
    parser.add_argument("--file", type=Path, default=TAXONOMY_PATH)
    parser.add_argument("--dry-run", action="store_true", help="только показать план")
    parser.add_argument(
        "--deactivate-extra",
        action="store_true",
        help="выключить (is_active: false) оси и значения, которых нет в файле",
    )
    args = parser.parse_args(argv)

    desired = json.loads(args.file.read_text(encoding="utf-8"))["facets"]

    if not args.email or not args.password:
        print("нужны --email/--password (или BOOTSTRAP_ADMIN_* в окружении)", file=sys.stderr)
        return 2

    with httpx.Client(base_url=args.base_url, timeout=30.0) as client:
        client.headers["Authorization"] = f"Bearer {_token(client, args.email, args.password)}"
        response = client.get("/api/v1/admin/facets")
        response.raise_for_status()
        plan = plan_changes(response.json(), desired)

        sources = client.get("/api/v1/admin/sources")
        sources.raise_for_status()
        plan.patch_sources, plan.missing_sources = plan_sources(
            sources.json(), source_defaults(desired)
        )

        print(describe(plan, args.deactivate_extra))
        if args.dry_run or not plan.has_work(args.deactivate_extra):
            return 0
        apply(client, plan, args.deactivate_extra)
        print("\nготово")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
