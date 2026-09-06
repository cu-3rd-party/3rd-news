from pathlib import Path

from ..core.config import Settings, get_settings
from ..infra.clients.admin import Admin
from ..interactor.use_cases.copy_labels import describe as describe_transfers
from ..interactor.use_cases.copy_labels import plan_transfers
from ..interactor.use_cases.duplicates import copy_pairs, find_groups, load_posts
from ..interactor.use_cases.duplicates import describe as describe_duplicates
from ..interactor.use_cases.facets import human_facets, labelled, source_driven
from ..interactor.use_cases.gold import describe as describe_gold
from ..interactor.use_cases.gold import golden
from ..interactor.use_cases.progress import report
from ..interactor.use_cases.reject_noise import describe as describe_noise
from ..interactor.use_cases.reject_noise import find_candidates
from ..interactor.use_cases.release_facet import describe as describe_facet
from ..interactor.use_cases.release_facet import pinned
from ..interactor.use_cases.sample import candidates, pick
from ..interactor.use_cases.sample import describe as describe_sample


def admin(settings: Settings) -> Admin:
    email = settings.admin_email
    password = settings.admin_password.get_secret_value()
    if not email or not password:
        raise RuntimeError("administrator credentials are required")
    return Admin.connect(settings.main_url, email, password)


def copy_labels(settings: Settings) -> int:
    with admin(settings) as client:
        items = [item for item in client.news() if item.get("status") != "rejected"]
        transfers = plan_transfers(items, settings.corpus_threshold)
        print(describe_transfers(transfers))
        if settings.corpus_apply:
            for transfer in transfers:
                client.set_labels(transfer.target_id, transfer.labels)
            if settings.corpus_gold_copies:
                source_ids = {item["id"] for item in items if item.get("is_gold")}
                targets = sorted(
                    {item.target_id for item in transfers if item.origin_id in source_ids}
                )
                if targets:
                    client.set_gold(targets, True)
    return 0


def gold(settings: Settings) -> int:
    with admin(settings) as client:
        items = list(client.news())
        print(describe_gold(items))
        ids = [item["id"] for item in golden(items)]
        if settings.corpus_clear_gold and settings.corpus_apply:
            for start in range(0, len(ids), 200):
                client.set_gold(ids[start : start + 200], False)
    return 0


def duplicates(settings: Settings) -> int:
    posts = load_posts(settings.corpus_input_path)
    groups = find_groups(posts, settings.corpus_threshold)
    print(describe_duplicates(groups, len(posts)))
    if settings.corpus_output_path is not None:
        rows = ["copy_id\torigin_id\tsource_key"]
        rows.extend("\t".join(pair) for pair in copy_pairs(groups))
        settings.corpus_output_path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return 0


def progress(settings: Settings) -> int:
    with admin(settings) as client:
        items = list(client.news())
        sources = client.client.get("/api/v1/admin/sources")
        sources.raise_for_status()
    print(
        report(
            items,
            sources.json()["items"],
            settings.corpus_size,
            settings.corpus_seed,
            settings.corpus_threshold,
            settings.corpus_by_channel,
        )
    )
    return 0


def reject_noise(settings: Settings) -> int:
    with admin(settings) as client:
        items = list(client.news(status=settings.corpus_status))
        found = find_candidates(items)
        print(describe_noise(found, len(items)))
        if settings.corpus_apply:
            for candidate in found:
                client.set_status(candidate.id, "rejected")
    if settings.corpus_output_path is not None and settings.corpus_apply:
        settings.corpus_output_path.write_text(
            "\n".join(candidate.id for candidate in found) + "\n", encoding="utf-8"
        )
    return 0


def release_facet(settings: Settings) -> int:
    with admin(settings) as client:
        items = pinned(list(client.news()), settings.corpus_facet)
        print(describe_facet(items, settings.corpus_facet))
        if settings.corpus_apply:
            for item in items:
                client.client.put(
                    f"/api/v1/admin/news/{item['id']}/labels",
                    json={"labels": {}, "release_facets": [settings.corpus_facet]},
                ).raise_for_status()
    return 0


def sample(settings: Settings) -> int:
    with admin(settings) as client:
        items = list(client.news())
        response = client.client.get("/api/v1/admin/sources")
        response.raise_for_status()
        sources = response.json()["items"]
    pool = candidates(items, settings.corpus_threshold)
    keep: frozenset[str] = frozenset()
    if not settings.corpus_fresh:
        facets = human_facets(source_driven(sources))
        keep = frozenset(item["id"] for item in pool if labelled(item, facets) == set(facets))
    chosen = pick(pool, settings.corpus_size, settings.corpus_seed, settings.corpus_cap, keep)
    print(describe_sample(chosen, len(pool), len(items), len(keep)))
    if settings.corpus_output_path is not None:
        write_sample(settings.corpus_output_path, chosen)
    return 0


def write_sample(path: Path, chosen: list[dict]) -> None:
    rows = ["id\tsource_key\tpublished_at\ttitle"]
    for item in chosen:
        title = " ".join((item.get("title") or "").split())[:80]
        rows.append(
            "\t".join(
                [
                    item["id"],
                    item.get("source_key") or "",
                    (item.get("published_at") or "")[:10],
                    title,
                ]
            )
        )
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def main() -> int:
    settings = get_settings()
    actions = {
        "copy-labels": copy_labels,
        "duplicates": duplicates,
        "gold": gold,
        "progress": progress,
        "reject-noise": reject_noise,
        "release-facet": release_facet,
        "sample": sample,
    }
    return actions[settings.corpus_action](settings)
