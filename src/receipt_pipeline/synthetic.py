"""SYNTHETIC CI data only. Never used as a live extraction or benchmark result."""

from receipt_pipeline import store
from receipt_pipeline.schema import Receipt


def receipt_dict():
    def obs(value):
        return {
            "value": value,
            "evidence": {"span": str(value), "region": []},
            "confidence": 0.95,
            "model": "synthetic-fixture",
            "prompt_version": "fixture-v1",
        }

    return {
        "merchant": obs("Synthetic Cafe"),
        "date": obs("2026-01-01"),
        "line_items": [{"name": obs("Coffee"), "quantity": obs("2"), "amount": obs("100")}],
        "subtotal": obs("100"),
        "tax": obs("10"),
        "total": obs("110"),
    }


def seed_database(conn):
    store.ingest(
        conn,
        {
            "revision": "synthetic-ci",
            "receipts": [
                {
                    "id": "synthetic-1",
                    "image": "synthetic-no-image",
                    "sha256": "synthetic",
                    "labels": {"synthetic": True},
                }
            ],
        },
    )
    store.save_extraction(
        conn,
        "synthetic-1",
        {
            "key": "synthetic-1",
            "model": "synthetic-fixture",
            "prompt_version": "fixture-v1",
            "receipt": Receipt.model_validate(receipt_dict()).model_dump(mode="json"),
            "origin": "synthetic",
            "cost_usd": 0,
            "latency_s": 0,
            "error": None,
        },
    )
    store.validate_all(conn)
