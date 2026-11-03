from decimal import Decimal

import pytest

from extraction_evals import dataset, normalize
from extraction_evals.extractors.baseline import BaselineExtractor
from extraction_evals.schema import FIELDS, Extracted, InvoiceExtraction, empty_extraction
from extraction_evals.scoring import is_grounded, score_document, score_run, summarize


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1,234.50", Decimal("1234.50")),
        ("1.234,50", Decimal("1234.50")),
        ("3.450.000", Decimal("3450000")),
        ("450.000", Decimal("450000")),
        ("S/ 99,90", Decimal("99.90")),
        ("1416.00", Decimal("1416.00")),
        ("not a number", None),
        (None, None),
    ],
)
def test_amounts_in_any_format(raw, expected) -> None:
    assert normalize.amount(raw) == expected


def test_same_compares_meaning_not_format() -> None:
    assert normalize.same("total_amount", "1.234,50", "1234.5")
    assert normalize.same("vendor_tax_id", "20-1234 5678", "2012345678")
    assert normalize.same("currency", "S/", "PEN")
    assert normalize.same("vendor_name", "  andes   freight llc", "Andes Freight LLC")
    assert normalize.same("due_date", None, None)
    assert not normalize.same("issue_date", "2026-13-01", "2026-01-13")
    assert not normalize.same("total_amount", None, "10.00")


def test_dataset_is_deterministic_and_balanced() -> None:
    docs = dataset.generate()

    assert docs == dataset.generate()
    assert len(docs) == len(dataset.LAYOUTS) * dataset.DOCS_PER_LAYOUT
    assert {d.layout for d in docs} == {"us", "peru", "mexico", "email"}
    assert all(set(d.gold) == set(FIELDS) for d in docs)
    assert all(d.gold["due_date"] is None for d in docs if d.layout == "mexico")


def test_dataset_round_trips_through_jsonl(tmp_path) -> None:
    docs = dataset.generate(per_layout=2)
    dataset.save(docs, tmp_path / "d.jsonl")

    assert dataset.load(tmp_path / "d.jsonl") == docs


def test_perfect_prediction_is_accepted_and_correct() -> None:
    doc = dataset.generate(per_layout=1)[0]
    perfect = InvoiceExtraction(**{f: Extracted(value=doc.gold[f], evidence=doc.text.splitlines()[0]) for f in FIELDS})

    score = score_document(doc, perfect)

    assert score.all_correct and score.auto_accepted


def test_invented_evidence_is_not_grounded() -> None:
    text = "Total due: $10.00"

    assert is_grounded("total_amount", "10.00", "Total due:   $10.00", text)  # spacing is forgiven
    assert not is_grounded("total_amount", "10.00", "Total: $10.00", text)
    assert not is_grounded("total_amount", "10.00", None, text)
    assert not is_grounded("total_amount", None, None, text)  # required and missing
    assert is_grounded("due_date", None, None, text)  # optional and absent


def test_baseline_falls_into_the_traps() -> None:
    docs = dataset.generate()
    extractor = BaselineExtractor()

    summary = score_run(extractor.name, docs, {d.id: extractor.extract(d.id, d.text) for d in docs})

    assert summary.layout_accuracy["mexico"] == 1.0
    assert summary.layout_accuracy["us"] == 0.0  # picks the customer's tax ID
    assert summary.layout_accuracy["peru"] == 0.0  # reads the customer RUC
    assert summary.auto_accepted_accuracy < 0.5  # confident and wrong: why evidence alone is not enough


def test_empty_predictions_score_zero_and_go_to_review() -> None:
    docs = dataset.generate(per_layout=1)

    summary = score_run("nothing", docs, {})

    assert summary.document_accuracy == 0.0
    assert summary.auto_accept_rate == 0.0
    assert summary.errors_sent_to_review == 1.0
    assert summary.auto_accepted_accuracy == 0.0  # no division by zero


def test_summary_of_no_documents() -> None:
    assert summarize("x", []).documents == 0


def test_empty_extraction_has_every_field() -> None:
    assert all(getattr(empty_extraction(), f).value is None for f in FIELDS)
