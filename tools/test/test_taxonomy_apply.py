from __future__ import annotations

import json
import re
from pathlib import Path

from tools.lib.interactor.use_cases.apply_taxonomy import (
    TAXONOMY_PATH,
    plan_changes,
    plan_sources,
    source_defaults,
)

DESIRED = json.loads(TAXONOMY_PATH.read_text(encoding="utf-8"))["facets"]
ROOT = Path(__file__).resolve().parents[2]


def facet(slug="topic", title="Тема", values=(), **extra):
    return {"slug": slug, "title": title, "type": "single", "values": list(values), **extra}


def test_empty_admin_gets_every_facet_created():
    plan = plan_changes([], DESIRED)

    assert [spec["slug"] for spec in plan.create_facets] == [
        "topic",
        "action",
        "importance",
        "audience",
        "program",
    ]
    assert not plan.patch_facets and not plan.create_values and not plan.patch_values
    assert plan.has_work()


def test_matching_admin_needs_no_changes():
    existing = [
        {
            "id": f"f{i}",
            **facet(
                slug=spec["slug"],
                title=spec["title"],
                type=spec["type"],
                ai_hint=spec["ai_hint"],
                values=[
                    {
                        "id": f"v{i}{j}",
                        "slug": value["slug"],
                        "title": value["title"],
                        "ai_hint": value["ai_hint"],
                        "synonyms": value["synonyms"],
                        "match_patterns": value["match_patterns"],
                        "position": j,
                    }
                    for j, value in enumerate(spec["values"])
                ],
                position=spec["position"],
            ),
        }
        for i, spec in enumerate(DESIRED)
    ]

    plan = plan_changes(existing, DESIRED)

    assert not plan.has_work(deactivate=True)
    assert plan.deactivate_facets == [] and plan.deactivate_values == []


def test_changed_hint_and_new_value_are_planned():
    spec = DESIRED[1]
    existing = [
        {
            "id": "f1",
            "slug": spec["slug"],
            "title": spec["title"],
            "type": spec["type"],
            "ai_hint": "старая подсказка",
            "position": spec["position"],
            "values": [
                {
                    "id": "v1",
                    "slug": spec["values"][0]["slug"],
                    "title": spec["values"][0]["title"],
                    "ai_hint": spec["values"][0]["ai_hint"],
                    "synonyms": [],
                    "match_patterns": spec["values"][0]["match_patterns"],
                    "position": 0,
                }
            ],
        }
    ]

    plan = plan_changes(existing, [spec])

    assert [(p.id, p.label, p.changed) for p in plan.patch_facets] == [
        ("f1", "action", {"ai_hint": spec["ai_hint"]})
    ]
    assert [value["slug"] for _, _, value in plan.create_values] == ["optional", "fyi"]
    assert [(p.id, p.label, p.changed) for p in plan.patch_values] == [
        ("v1", "action.deadline", {"synonyms": spec["values"][0]["synonyms"]})
    ]


def test_position_comes_from_the_file_so_the_screen_matches_the_guideline():

    spec = DESIRED[1]
    existing = [
        {
            "id": "f1",
            "slug": "action",
            "title": spec["title"],
            "type": spec["type"],
            "ai_hint": spec["ai_hint"],
            "position": 0,
            "values": [],
        }
    ]

    plan = plan_changes(existing, [spec])

    assert plan.patch_facets[0].changed == {"position": spec["position"]}


def test_patch_sends_the_whole_record_because_patch_replaces_it():

    spec = DESIRED[1]
    existing = [
        {
            "id": "f1",
            "slug": "action",
            "title": spec["title"],
            "type": spec["type"],
            "ai_hint": "старая подсказка",
            "description": "не терять",
            "required": True,
            "is_active": True,
            "position": 7,
            "values": [],
        }
    ]

    payload = plan_changes(existing, [spec]).patch_facets[0].payload

    assert payload["ai_hint"] == spec["ai_hint"]
    assert payload["description"] == "не терять"
    assert payload["position"] == spec["position"]
    assert payload["required"] is True
    assert payload["slug"] == "action"


def test_unknown_facets_and_values_are_only_deactivated_never_deleted():
    existing = [
        {"id": "f9", "slug": "stream", "title": "Поток", "type": "multi", "values": []},
        {
            "id": "f1",
            "slug": "topic",
            "title": DESIRED[0]["title"],
            "type": "single",
            "ai_hint": DESIRED[0]["ai_hint"],
            "values": [
                {
                    "id": "v9",
                    "slug": "legacy",
                    "title": "Старое",
                    "synonyms": [],
                    "match_patterns": [],
                }
            ],
        },
    ]

    plan = plan_changes(existing, [DESIRED[0]])

    assert [p.label for p in plan.deactivate_facets] == ["stream"]
    assert [p.label for p in plan.deactivate_values] == ["topic.legacy"]
    assert plan.deactivate_facets[0].payload["is_active"] is False
    assert plan.deactivate_facets[0].payload["title"] == "Поток"


def test_deactivation_is_work_only_with_the_flag():
    existing = [{"id": "f9", "slug": "stream", "title": "Поток", "type": "multi", "values": []}]

    plan = plan_changes(existing, [])

    assert not plan.has_work()
    assert plan.has_work(deactivate=True)


def test_already_inactive_entries_are_not_touched_again():
    existing = [
        {
            "id": "f9",
            "slug": "stream",
            "title": "Поток",
            "type": "multi",
            "is_active": False,
            "values": [],
        }
    ]

    plan = plan_changes(existing, [])

    assert plan.deactivate_facets == []
    assert not plan.has_work(deactivate=True)


def test_taxonomy_file_is_well_formed():
    assert [spec["slug"] for spec in DESIRED] == [
        "topic",
        "action",
        "importance",
        "audience",
        "program",
    ]
    for spec in DESIRED:
        assert spec["type"] in {"single", "multi"}
        assert spec["ai_hint"]
        slugs = [value["slug"] for value in spec["values"]]
        assert len(slugs) == len(set(slugs)), spec["slug"]
        for value in spec["values"]:
            assert value["title"] and value["ai_hint"], value["slug"]
            for pattern in value["match_patterns"]:
                re.compile(pattern)


def test_axes_match_the_annotation_guideline():
    guideline = (ROOT / "docs/annotation-guideline.md").read_text(encoding="utf-8")
    for spec in DESIRED:
        for value in spec["values"]:
            assert f"`{spec['slug']}.{value['slug']}`" in guideline, value["slug"]


def test_program_is_filled_from_channels_not_from_text():

    program = next(spec for spec in DESIRED if spec["slug"] == "program")

    assert program["type"] == "multi"
    for value in program["values"]:
        assert value["synonyms"] == [] and value["match_patterns"] == []
        assert value["source_keys"], value["slug"]


def test_every_channel_belongs_to_at_most_one_program():
    wanted = source_defaults(DESIRED)

    for source_key, facets in wanted.items():
        assert set(facets) == {"program"}, source_key
    seen = [key for facets in wanted.values() for key in facets["program"]]
    assert len(seen) == len(set(seen)), "значение program привязано к двум каналам"


def test_source_defaults_merge_several_values_for_one_channel():
    desired = [
        {
            "slug": "program",
            "values": [
                {"slug": "ai-2025", "source_keys": ["shared"]},
                {"slug": "swe-2025", "source_keys": ["shared", "only-swe"]},
            ],
        }
    ]

    assert source_defaults(desired) == {
        "shared": {"program": ["ai-2025", "swe-2025"]},
        "only-swe": {"program": ["swe-2025"]},
    }


def test_plan_sources_patches_only_what_differs_and_keeps_other_facets():
    existing = [
        {
            "id": "s1",
            "slug": "ai",
            "title": "Направление ИИ",
            "kind": "telegram",
            "skip_classification": False,
            "default_labels": {"importance": ["useful"]},
        },
        {
            "id": "s2",
            "slug": "swe",
            "title": "Разработка",
            "default_labels": {"program": ["swe-2025"]},
        },
    ]
    wanted = {
        "ai": {"program": ["ai-2025"]},
        "swe": {"program": ["swe-2025"]},
        "gone": {"program": ["x"]},
    }

    patches, missing = plan_sources(existing, wanted)

    assert [(p.id, p.label) for p in patches] == [("s1", "ai")]
    assert patches[0].changed == {
        "default_labels": {"importance": ["useful"], "program": ["ai-2025"]}
    }
    assert missing == ["gone"]


def test_source_patch_carries_the_whole_record():

    existing = [
        {
            "id": "s1",
            "slug": "ai",
            "title": "Направление ИИ",
            "kind": "telegram",
            "url": "https://time.cu.ru/ai",
            "is_active": True,
            "skip_classification": False,
            "default_labels": {},
        }
    ]

    payload = plan_sources(existing, {"ai": {"program": ["ai-2025"]}})[0][0].payload

    assert payload["title"] == "Направление ИИ"
    assert payload["kind"] == "telegram" and payload["url"] == "https://time.cu.ru/ai"
    assert payload["skip_classification"] is False
    assert payload["default_labels"] == {"program": ["ai-2025"]}
