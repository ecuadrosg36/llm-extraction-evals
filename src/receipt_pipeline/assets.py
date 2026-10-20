from pathlib import Path

from dagster import AssetCheckResult, Definitions, asset, asset_check

from receipt_pipeline import store
from receipt_pipeline.cli import dbt_build, run_extract
from receipt_pipeline.evaluate import evaluate
from receipt_pipeline.sample import load_manifest


@asset
def ingest():
    """Download explicitly with receipts download before materializing."""
    manifest = load_manifest()
    with store.connect() as conn:
        store.ingest(conn, manifest)
    return len(manifest["receipts"])


@asset(deps=[ingest])
def extract():
    """Cache-only by design. Paid warmup is an explicit CLI action."""
    return run_extract(Path("data"))


@asset(deps=[extract])
def validate():
    with store.connect() as conn:
        store.validate_all(conn)
        return conn.execute(
            "select count(*) from raw.extractions where status='rejected'"
        ).fetchone()[0]


@asset(deps=[validate])
def dbt():
    dbt_build()


@asset(deps=[dbt])
def evals(extract):
    return evaluate(load_manifest(), extract)


@asset_check(asset=ingest, blocking=True)
def fixed_sample(ingest):
    return AssetCheckResult(passed=ingest == 200, metadata={"receipts": ingest})


@asset_check(asset=validate)
def quality_gate(validate):
    # Rejected receipts are quarantined, not silently dropped; fail signals review workload.
    return AssetCheckResult(passed=validate == 0, metadata={"review_required": validate})


defs = Definitions(
    assets=[ingest, extract, validate, dbt, evals], asset_checks=[fixed_sample, quality_gate]
)
