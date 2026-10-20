"""All receipt payloads here are synthetic, not recorded Anthropic outputs."""

import json
import os
from copy import deepcopy
from decimal import Decimal

import pytest

from receipt_pipeline.evaluate import cord_targets, deepeval_score, evaluate, exact
from receipt_pipeline.extract import Extractor, request_key
from receipt_pipeline.sample import selected_indices
from receipt_pipeline.schema import Receipt, money, validate
from receipt_pipeline.synthetic import receipt_dict


def test_parse_synthetic_and_arithmetic():
    data = receipt_dict()
    receipt = Receipt.model_validate(data)
    assert receipt.subtotal.value == Decimal(100)
    assert validate(receipt) == []
    data["total"]["value"] = "111"
    data["subtotal"]["value"] = "101"
    reasons = validate(Receipt.model_validate(data))
    assert "items_sum_ne_subtotal" in reasons
    assert "subtotal_plus_tax_ne_total" not in reasons  # 101 + 10 = 111


@pytest.mark.parametrize(
    "field,value,reason",
    [
        ("date", "not-a-date", "unparseable_date"),
        ("date", "2026-02-30", "unparseable_date"),
        ("total", "111", "subtotal_plus_tax_ne_total"),
        ("tax", None, "missing_totals"),
    ],
)
def test_rejections(field, value, reason):
    data = receipt_dict()
    data[field]["value"] = value
    assert reason in validate(Receipt.model_validate(data))


def test_confidence_evidence_and_provenance():
    data = receipt_dict()
    data["merchant"]["confidence"] = 0.2
    data["merchant"]["evidence"] = {"span": "", "region": [1, 0, 0, 1]}
    reasons = validate(Receipt.model_validate(data))
    assert "low_confidence:merchant" in reasons
    assert "invalid_region:merchant" in reasons
    del data["tax"]["model"]
    with pytest.raises(ValueError):
        Receipt.model_validate(data)


@pytest.mark.parametrize(
    "text,want",
    [("25.000", "25000"), ("25,000", "25000"), ("25.000,50", "25000.50"), ("Rp 100", "100")],
)
def test_cord_money(text, want):
    assert money(text) == Decimal(want)


def test_fixed_sample():
    indices = selected_indices()
    assert len(indices) == len(set(indices)) == 200
    assert indices == selected_indices()
    assert min(indices) >= 0 and max(indices) < 800


def test_cache_never_calls_api(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    image = tmp_path / "synthetic.png"
    image.write_bytes(b"synthetic-not-an-image")
    extractor = Extractor(tmp_path)
    with pytest.raises(RuntimeError, match="live calls disabled"):
        extractor.run(image, "claude-haiku-5-5", "v1")
    key = request_key(image.read_bytes(), "claude-haiku-5-5", "v1")
    result = {"receipt": receipt_dict(), "origin": "synthetic"}
    (extractor.cache / f"{key}.json").write_text(json.dumps(result))
    assert extractor.run(image, "claude-haiku-5-5", "v1") == result
    assert key != request_key(image.read_bytes(), "claude-haiku-5-5", "v2")
    with pytest.raises(RuntimeError, match="Missing ANTHROPIC_API_KEY"):
        Extractor(tmp_path, live=True).run(image, "claude-sonnet-5-5", "v1")


def test_cord_coverage_and_exact():
    targets = cord_targets(
        {
            "gt_parse": {
                "sub_total": {"subtotal_price": "1.000"},
                "total": {"total_price": "1.100"},
                "menu": [{"nm": "Coffee", "price": "1.000"}],
            }
        }
    )
    assert "merchant" not in targets and "date" not in targets and "tax" not in targets
    assert exact("1000.00", targets["subtotal"]) == 1
    assert deepeval_score("1000.00", "1000") == 1
    assert deepeval_score(None, "1000") == 0


def test_evaluation_refuses_synthetic(tmp_path):
    with pytest.raises(ValueError, match="non-live"):
        evaluate(
            {"receipts": [{"id": "x"}]}, [("x", {"origin": "synthetic"})], tmp_path / "eval.json"
        )


@pytest.mark.postgres
@pytest.mark.skipif(os.getenv("RUN_POSTGRES_TESTS") != "1", reason="Postgres opt-in")
def test_review_and_idempotence():
    from psycopg.types.json import Jsonb

    from receipt_pipeline import store
    from receipt_pipeline.synthetic import seed_database

    with store.connect() as conn:
        seed_database(conn)
        seed_database(conn)
        assert (
            conn.execute(
                "select count(*) from raw.extractions where run_key='synthetic-1'"
            ).fetchone()[0]
            == 1
        )
        data = receipt_dict()
        data["merchant"]["confidence"] = 0.1
        conn.execute(
            "update raw.extractions set response=jsonb_set(response,'{receipt}',%s) "
            "where run_key='synthetic-1'",
            (Jsonb(data),),
        )
        conn.execute("delete from raw.corrections where run_key='synthetic-1'")
        conn.execute("delete from raw.review_queue where run_key='synthetic-1'")
        store.validate_all(conn)
        wrong = deepcopy(data)
        wrong["total"]["value"] = "999"
        with pytest.raises(ValueError, match="validation"):
            store.review(conn, "synthetic-1", "test-reviewer", Receipt.model_validate(wrong))
        store.review(conn, "synthetic-1", "test-reviewer", Receipt.model_validate(data))
        label = conn.execute(
            "select label from raw.corrections where run_key='synthetic-1'"
        ).fetchone()[0]
        assert label["merchant"]["value"] == "Synthetic Cafe"
        with pytest.raises(ValueError, match="pending"):
            store.review(conn, "synthetic-1", "test-reviewer")
        conn.rollback()
