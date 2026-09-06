import asyncio
import json

from thirdnews_contracts import Taxonomy

from ..core.config import Settings, get_settings
from ..domain.entities.prediction import Prediction
from ..domain.entities.record import Record
from ..dto.evaluation_report import EvaluationReport
from ..infra.clients.classifier_runtime import load_classifiers
from ..infra.clients.e5_embedder import E5Embedder
from ..infra.clients.fake_embedder import FakeEmbedder
from ..infra.storage.cached_embedder import CachedEmbedder
from ..interactor.use_cases.eval_dataset import load_context, load_records, load_taxonomy
from ..interactor.use_cases.eval_examples import select_knn, select_recent
from ..interactor.use_cases.eval_kappa import kappa_report, read_labels_csv, write_blind_csv
from ..interactor.use_cases.eval_metrics import summarize
from ..interactor.use_cases.eval_runners import build_request, combine, run_ai, run_regex


def embedder(settings: Settings) -> CachedEmbedder:
    inner = (
        FakeEmbedder()
        if settings.eval_embedder == "fake"
        else E5Embedder(settings.eval_embedding_model)
    )
    tag = (
        "fake"
        if settings.eval_embedder == "fake"
        else settings.eval_embedding_model.replace("/", "__")
    )
    return CachedEmbedder(inner, settings.eval_cache_path / "emb" / tag)


async def predict_all(
    settings: Settings,
) -> tuple[list[Record], Taxonomy, dict[str, Prediction]]:
    records = load_records(settings.eval_data_path)
    taxonomy = load_taxonomy(settings.eval_taxonomy_path)
    context = load_context(settings.eval_context_path)
    targets = (
        [record for record in records if record.is_gold] if settings.eval_only_gold else records
    )
    regex_module, ai_module = load_classifiers()
    cached_embedder = embedder(settings) if settings.eval_examples == "knn" else None
    config = {"model": settings.eval_model} if settings.eval_model else {}
    predictions: dict[str, Prediction] = {}
    for record in targets:
        if settings.eval_examples == "none":
            examples = []
        elif settings.eval_examples == "recent":
            examples = select_recent(record, records, settings.eval_k)
        else:
            if cached_embedder is None:
                raise RuntimeError("kNN examples require an embedder")
            examples = select_knn(record, records, settings.eval_k, cached_embedder)
        request = build_request(
            record,
            taxonomy,
            examples,
            context,
            config,
            settings.eval_min_confidence,
        )
        if settings.eval_classifier == "regex":
            prediction = run_regex(request, regex_module)
        elif settings.eval_classifier == "ai":
            prediction = await run_ai(request, ai_module, settings.eval_cache_path / "llm")
        else:
            prediction = combine(
                run_regex(request, regex_module),
                await run_ai(request, ai_module, settings.eval_cache_path / "llm"),
                taxonomy,
                regex_threshold=settings.eval_regex_threshold,
                ai_threshold=settings.eval_ai_threshold,
            )
        predictions[record.id] = prediction
    return targets, taxonomy, predictions


def run(settings: Settings) -> int:
    records, taxonomy, predictions = asyncio.run(predict_all(settings))
    summary = summarize(records, predictions, taxonomy)
    payload = EvaluationReport(
        name=settings.eval_output_path.stem,
        params=settings.model_dump(mode="json"),
        summary=summary,
    )
    settings.eval_output_path.parent.mkdir(parents=True, exist_ok=True)
    settings.eval_output_path.write_text(payload.model_dump_json(indent=2))
    print_summary(settings.eval_output_path.stem, summary)
    return 0


def compare(settings: Settings) -> int:
    rows = [json.loads(path.read_text()) for path in settings.eval_result_paths]
    facets = sorted({facet["facet"] for row in rows for facet in row["summary"]["facets"]})
    table = [["run", *[f"{facet} exact/F1" for facet in facets], "latency", "tokens"]]
    for row in rows:
        by_slug = {facet["facet"]: facet for facet in row["summary"]["facets"]}
        cells = [row["name"]]
        for facet in facets:
            report = by_slug.get(facet)
            cells.append(f"{report['exact']:.3f}/{report['macro_f1']:.3f}" if report else "—")
        summary = row["summary"]
        cells.extend(
            [
                f"{summary['avg_latency_s']:.2f}s",
                str(summary["prompt_tokens"] + summary["completion_tokens"]),
            ]
        )
        table.append(cells)
    widths = [max(len(row[index]) for row in table) for index in range(len(table[0]))]
    for row in table:
        print("  ".join(cell.ljust(widths[index]) for index, cell in enumerate(row)))
    return 0


def blind(settings: Settings) -> int:
    records = load_records(settings.eval_data_path)
    taxonomy = load_taxonomy(settings.eval_taxonomy_path)
    write_blind_csv(
        records,
        taxonomy,
        settings.eval_output_path,
        n=settings.eval_sample_size,
        seed=settings.eval_seed,
    )
    return 0


def kappa(settings: Settings) -> int:
    if settings.eval_other_path is None:
        raise RuntimeError("EVAL_OTHER_PATH is required")
    records = load_records(settings.eval_data_path)
    taxonomy = load_taxonomy(settings.eval_taxonomy_path)
    report = kappa_report(records, read_labels_csv(settings.eval_other_path), taxonomy)
    for facet, item in report.items():
        value = "—" if item["kappa"] is None else f"{item['kappa']:.3f}"
        print(f"{facet} n={item['n']} kappa={value} расхождений={len(item['disagreements'])}")
    return 0


def print_summary(name: str, summary: dict) -> None:
    print(
        f"== {name}: n={summary['n']}, latency={summary['avg_latency_s']:.2f}s, "
        f"tokens={summary['prompt_tokens']}+{summary['completion_tokens']}, "
        f"cache_hits={summary['cache_hits']}"
    )
    for facet in summary["facets"]:
        print(
            f"  {facet['facet']} exact={facet['exact']:.3f} "
            f"macroF1={facet['macro_f1']:.3f} (n={facet['n']})"
        )


def main() -> int:
    settings = get_settings()
    actions = {"run": run, "compare": compare, "blind": blind, "kappa": kappa}
    return actions[settings.eval_action](settings)
