import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from receipt_pipeline import store
from receipt_pipeline.evaluate import VARIANTS, evaluate
from receipt_pipeline.extract import Extractor, estimate
from receipt_pipeline.sample import download, load_manifest
from receipt_pipeline.schema import Receipt


def run_extract(root, live=False, limit=None):
    manifest = load_manifest(root)
    extractor = Extractor(root, live=live)
    responses = []
    for row in manifest["receipts"][:limit]:
        image_path = Path(row["image"])
        if hashlib.sha256(image_path.read_bytes()).hexdigest() != row["sha256"]:
            raise ValueError(f"Image content changed: {row['id']}")
        for model, prompt in VARIANTS:
            response = extractor.run(image_path, model, prompt)
            with store.connect() as conn:
                store.save_extraction(conn, row["id"], response)
            responses.append((row["id"], response))
    return responses


def dbt_build():
    subprocess.run(["dbt", "build", "--project-dir", "dbt", "--profiles-dir", "dbt"], check=True)


def main():
    parser = argparse.ArgumentParser(description="Auditable CORD receipt pipeline")
    parser.add_argument(
        "command",
        choices=[
            "download",
            "ingest",
            "extract",
            "validate",
            "dbt",
            "eval",
            "estimate",
            "demo",
            "queue",
            "review",
            "export-labels",
            "ci-seed",
        ],
    )
    parser.add_argument("--root", type=Path, default=Path("data"))
    parser.add_argument("--live", action="store_true", help="Explicit paid API authorization")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--key")
    parser.add_argument("--reviewer")
    parser.add_argument("--correction", type=Path)
    parser.add_argument("--output", type=Path, default=Path("data/corrections.json"))
    args = parser.parse_args()
    command, root = args.command, args.root
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")
    if command == "download":
        download(root)
    elif command == "estimate":
        print(
            json.dumps(
                {
                    "conservative_usd": sum(estimate(m, args.limit or 200) for m, _ in VARIANTS),
                    "cap_usd": 5,
                }
            )
        )
    elif command in ("ingest", "ci-seed"):
        with store.connect() as conn:
            if command == "ci-seed":
                from receipt_pipeline.synthetic import seed_database

                seed_database(conn)
            else:
                store.ingest(conn, load_manifest(root))
    elif command == "extract":
        run_extract(root, args.live, args.limit)
    elif command == "validate":
        with store.connect() as conn:
            store.validate_all(conn)
    elif command == "dbt":
        dbt_build()
    elif command == "eval":
        evaluate(
            load_manifest(root), run_extract(root, False, args.limit), root / "evaluation.json"
        )
    elif command == "demo":
        # Requires sample + real response cache prepared separately; cannot spend accidentally.
        with store.connect() as conn:
            store.ingest(conn, load_manifest(root))
        responses = run_extract(root, False, 20)
        with store.connect() as conn:
            store.validate_all(conn)
        dbt_build()
        evaluate(load_manifest(root), responses, root / "demo-evaluation.json")
    elif command == "queue":
        with store.connect() as conn:
            for row in conn.execute(
                "select run_key,reasons from raw.review_queue "
                "where status='pending' order by run_key"
            ):
                print(json.dumps({"key": row[0], "reasons": row[1]}))
    elif command == "review":
        if not args.key or not args.reviewer:
            parser.error("review requires --key and --reviewer")
        corrected = (
            Receipt.model_validate_json(args.correction.read_text()) if args.correction else None
        )
        with store.connect() as conn:
            store.review(conn, args.key, args.reviewer, corrected)
    elif command == "export-labels":
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with store.connect() as conn:
            store.export_labels(conn, args.output)


if __name__ == "__main__":
    main()
