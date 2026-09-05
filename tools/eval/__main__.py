"""`python -m tools.eval` — run / compare / blind / kappa."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from .dataset import load_context, load_records, load_taxonomy
from .examples import CachedEmbedder, E5Embedder, FakeEmbedder, select_knn, select_recent
from .kappa import kappa_report, read_labels_csv, write_blind_csv
from .metrics import summarize
from .runners import Prediction, build_request, combine, load_classifiers, run_ai, run_regex


def _embedder(kind: str, model: str, cache_dir: Path) -> CachedEmbedder:
    inner = FakeEmbedder() if kind == "fake" else E5Embedder(model)
    tag = "fake" if kind == "fake" else model.replace("/", "__")
    return CachedEmbedder(inner, cache_dir / "emb" / tag)


async def _predict_all(args, targets, pool, taxonomy, context) -> dict[str, Prediction]:
    regex_module, ai_module = load_classifiers()
    embedder = (
        _embedder(args.embedder, args.embedding_model, args.cache_dir)
        if args.examples == "knn"
        else None
    )
    config = {"model": args.model} if args.model else {}
    predictions: dict[str, Prediction] = {}

    for index, record in enumerate(targets, 1):
        if args.examples == "none":
            examples = []
        elif args.examples == "recent":
            examples = select_recent(record, pool, args.k)
        else:
            examples = select_knn(record, pool, args.k, embedder)

        request = build_request(record, taxonomy, examples, context, config, args.min_confidence)
        if args.classifier == "regex":
            prediction = run_regex(request, regex_module)
        elif args.classifier == "ai":
            prediction = await run_ai(request, ai_module, args.cache_dir / "llm")
        else:
            prediction = combine(
                run_regex(request, regex_module),
                await run_ai(request, ai_module, args.cache_dir / "llm"),
                taxonomy,
                regex_threshold=args.regex_threshold,
                ai_threshold=args.ai_threshold,
            )
        predictions[record.id] = prediction
        print(f"\r{index}/{len(targets)}", end="", file=sys.stderr, flush=True)
    print(file=sys.stderr)
    return predictions


def cmd_run(args) -> int:
    records = load_records(args.data)
    taxonomy = load_taxonomy(args.taxonomy)
    context = load_context(args.context)
    # Leave-one-out: пул примеров — весь набор, сам пост из своих примеров
    # исключают select_recent / select_knn. Тест — весь набор или только золото.
    pool = records
    targets = [r for r in records if r.is_gold] if args.only_gold else records
    if not targets:
        print("нет постов для прогона (пустой набор или нет золотых)", file=sys.stderr)
        return 1

    predictions = asyncio.run(_predict_all(args, targets, pool, taxonomy, context))
    summary = summarize(targets, predictions, taxonomy)
    name = args.out.stem
    params = {
        key: (str(value) if isinstance(value, Path) else value)
        for key, value in vars(args).items()
        if key != "func"
    }
    payload = {"name": name, "params": params, "summary": summary}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    _print_summary(name, summary)
    return 0


def _print_summary(name: str, summary: dict) -> None:
    print(
        f"== {name}: n={summary['n']}, latency={summary['avg_latency_s']:.2f}s, "
        f"tokens={summary['prompt_tokens']}+{summary['completion_tokens']}, "
        f"cache_hits={summary['cache_hits']}"
    )
    for facet in summary["facets"]:
        print(
            f"  {facet['facet']:<14} exact={facet['exact']:.3f} "
            f"macroF1={facet['macro_f1']:.3f} (n={facet['n']})"
        )
        for value, m in facet["per_value"].items():
            print(
                f"      {value:<12} P={m['precision']:.2f} R={m['recall']:.2f} "
                f"F1={m['f1']:.2f} support={int(m['support'])}"
            )
    cells = []
    for b in summary["calibration"]:
        accuracy = "—" if b["accuracy"] is None else f"{b['accuracy']:.2f}"
        cells.append(f"[{b['lo']:.1f},{b['hi']:.1f}) n={b['n']} acc={accuracy}")
    print("  calibration:", ", ".join(cells))


def cmd_compare(args) -> int:
    rows = [json.loads(Path(p).read_text(encoding="utf-8")) for p in args.results]
    facets = sorted({f["facet"] for row in rows for f in row["summary"]["facets"]})
    header = ["run", *[f"{f} exact/F1" for f in facets], "latency", "tokens"]
    table = [header]
    for row in rows:
        by = {f["facet"]: f for f in row["summary"]["facets"]}
        cells = [row["name"]]
        for facet in facets:
            f = by.get(facet)
            cells.append(f"{f['exact']:.3f}/{f['macro_f1']:.3f}" if f else "—")
        s = row["summary"]
        cells += [f"{s['avg_latency_s']:.2f}s", f"{s['prompt_tokens'] + s['completion_tokens']}"]
        table.append(cells)
    widths = [max(len(r[i]) for r in table) for i in range(len(header))]
    for r in table:
        print("  ".join(cell.ljust(widths[i]) for i, cell in enumerate(r)))
    return 0


def cmd_blind(args) -> int:
    records = load_records(args.data)
    taxonomy = load_taxonomy(args.taxonomy)
    ids = write_blind_csv(records, taxonomy, args.out, n=args.n, seed=args.seed)
    print(
        f"{len(ids)} постов → {args.out}. Соглашения: пусто — не размечал, "
        "'-' — нет значения, 'a;b' — несколько."
    )
    return 0


def cmd_kappa(args) -> int:
    records = load_records(args.data)
    taxonomy = load_taxonomy(args.taxonomy)
    report = kappa_report(records, read_labels_csv(args.other), taxonomy)
    for facet, item in report.items():
        kappa = "—" if item["kappa"] is None else f"{item['kappa']:.3f}"
        print(
            f"{facet:<14} n={item['n']:<4} kappa={kappa}  "
            f"расхождений={len(item['disagreements'])}"
        )
        for d in item["disagreements"][: args.show]:
            print(f"    {d['id']}: эталон={d['gold'] or ['-']} друг={d['other'] or ['-']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tools.eval")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="прогнать классификатор по набору")
    run.add_argument("--data", type=Path, required=True)
    run.add_argument("--taxonomy", type=Path, required=True)
    run.add_argument("--context", type=Path, default=None)
    run.add_argument("--classifier", choices=["regex", "ai", "combined"], required=True)
    run.add_argument("--examples", choices=["none", "recent", "knn"], default="none")
    run.add_argument("--k", type=int, default=8)
    run.add_argument("--model", default=None, help="имя модели OpenRouter для ai/combined")
    run.add_argument("--min-confidence", type=float, default=0.0)
    run.add_argument("--regex-threshold", type=float, default=0.6)
    run.add_argument("--ai-threshold", type=float, default=0.6)
    run.add_argument("--embedder", choices=["e5", "fake"], default="e5")
    run.add_argument("--embedding-model", default="intfloat/multilingual-e5-base")
    run.add_argument("--cache-dir", type=Path, default=Path("data/cache"))
    run.add_argument("--only-gold", action="store_true", help="тест — только is_gold")
    run.add_argument("--out", type=Path, required=True)
    run.set_defaults(func=cmd_run)

    compare = sub.add_parser("compare", help="таблица по нескольким прогонам")
    compare.add_argument("results", nargs="+")
    compare.set_defaults(func=cmd_compare)

    blind = sub.add_parser("blind", help="CSV без меток для второго разметчика")
    blind.add_argument("--data", type=Path, required=True)
    blind.add_argument("--taxonomy", type=Path, required=True)
    blind.add_argument("--n", type=int, default=100)
    blind.add_argument("--seed", type=int, default=1)
    blind.add_argument("--out", type=Path, required=True)
    blind.set_defaults(func=cmd_blind)

    kappa = sub.add_parser("kappa", help="согласие с второй разметкой")
    kappa.add_argument("--data", type=Path, required=True)
    kappa.add_argument("--taxonomy", type=Path, required=True)
    kappa.add_argument("--other", type=Path, required=True)
    kappa.add_argument("--show", type=int, default=20)
    kappa.set_defaults(func=cmd_kappa)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
