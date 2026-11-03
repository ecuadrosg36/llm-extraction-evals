"""evals generate | run | score | gate

evals generate                                   # write data/invoices.jsonl
evals run --extractor baseline                   # extract, save runs/baseline.jsonl, print scores
evals run --extractor claude                     # needs ANTHROPIC_API_KEY
evals run --extractor gemini --model <model id>  # needs GEMINI_API_KEY
evals score runs/*.jsonl                         # compare saved runs, no API calls
evals gate runs/claude.jsonl --min-accuracy 0.95 # exit 1 if a run is below the bar (for CI)
"""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from extraction_evals import dataset
from extraction_evals.extractors import Extractor
from extraction_evals.report import pct, to_markdown
from extraction_evals.runs import load_run, save_run
from extraction_evals.scoring import Summary, score_run

DATA = Path("data/invoices.jsonl")
EXIT_OK, EXIT_BELOW_BAR = 0, 1


def make_extractor(kind: str, model: str | None) -> Extractor:
    if kind == "baseline":
        from extraction_evals.extractors.baseline import BaselineExtractor

        return BaselineExtractor()
    if kind == "claude":
        from extraction_evals.extractors.claude import DEFAULT_MODEL, ClaudeExtractor

        return ClaudeExtractor(model or DEFAULT_MODEL)
    if not model:
        raise SystemExit("evals: --model is required for gemini, e.g. --model <gemini model id>")
    from extraction_evals.extractors.gemini import GeminiExtractor

    return GeminiExtractor(model)


def _score_file(path: Path, documents: list[dataset.Document]) -> Summary:
    name, predictions = load_run(path)
    return score_run(name, documents, predictions)


def _run(args: argparse.Namespace) -> int:
    documents = dataset.load(args.data)
    extractor = make_extractor(args.extractor, args.model)
    predictions = {}
    for i, doc in enumerate(documents, start=1):
        predictions[doc.id] = extractor.extract(doc.id, doc.text)
        print(f"\r{i}/{len(documents)}", end="", file=sys.stderr)
    print(file=sys.stderr)
    out = args.out or Path("runs") / f"{args.extractor}.jsonl"
    save_run(out, extractor.name, predictions)
    print(f"saved {out}\n")
    print(to_markdown([score_run(extractor.name, documents, predictions)]))
    return EXIT_OK


def _gate(args: argparse.Namespace) -> int:
    summary = _score_file(args.run, dataset.load(args.data))
    accuracy = summary.overall_field_accuracy
    passed = accuracy >= args.min_accuracy
    verdict = "PASS" if passed else "FAIL"
    print(f"{verdict}: {summary.extractor} field accuracy {pct(accuracy)} (bar {pct(args.min_accuracy)})")
    return EXIT_OK if passed else EXIT_BELOW_BAR


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="evals", description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--data", type=Path, default=DATA)
    commands = parser.add_subparsers(dest="command", required=True)
    generate = commands.add_parser("generate")
    generate.add_argument("--seed", type=int, default=dataset.DEFAULT_SEED)
    run = commands.add_parser("run")
    run.add_argument("--extractor", choices=("baseline", "claude", "gemini"), required=True)
    run.add_argument("--model")
    run.add_argument("--out", type=Path)
    score = commands.add_parser("score")
    score.add_argument("runs", type=Path, nargs="+")
    gate = commands.add_parser("gate")
    gate.add_argument("run", type=Path)
    gate.add_argument("--min-accuracy", type=float, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "generate":
        dataset.save(dataset.generate(args.seed), args.data)
        print(f"wrote {args.data}")
        return EXIT_OK
    if args.command == "run":
        return _run(args)
    if args.command == "score":
        documents = dataset.load(args.data)
        print(to_markdown([_score_file(path, documents) for path in args.runs]))
        return EXIT_OK
    return _gate(args)


if __name__ == "__main__":
    sys.exit(main())
