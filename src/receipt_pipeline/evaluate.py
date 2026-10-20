"""No judge LLM: CORD-supported fields only, explicit denominators and missing labels."""

import json
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

from receipt_pipeline.schema import Receipt, money

VARIANTS = [("claude-haiku-5-5", "v1"), ("claude-haiku-5-5", "v2"), ("claude-sonnet-5-5", "v2")]
FIELDS = ("merchant", "date", "line_items", "subtotal", "tax", "total")


def cord_targets(labels):
    gt = labels.get("gt_parse", labels)
    subtotal = gt.get("sub_total", {})
    total = gt.get("total", {})
    # CORD-v2 does not reliably label merchant/date. Never treat missing as null truth.
    targets = {}
    for field, raw in (
        ("subtotal", subtotal.get("subtotal_price")),
        ("tax", subtotal.get("tax_price")),
        ("total", total.get("total_price")),
    ):
        if isinstance(raw, str):
            try:
                targets[field] = str(money(raw))
            except ValueError:
                pass
    menu = gt.get("menu")
    if isinstance(menu, dict):
        menu = [menu]
    if isinstance(menu, list) and menu:
        items = []
        try:
            for item in menu:
                name = item["nm"]
                if isinstance(name, list) and all(isinstance(x, str) for x in name):
                    name = " ".join(name)
                if not isinstance(name, str) or not isinstance(item["price"], str):
                    raise ValueError("ambiguous CORD menu value")
                items.append({"name": name.strip().casefold(), "amount": str(money(item["price"]))})
            targets["line_items"] = items
        except (KeyError, ValueError, TypeError):
            pass
    return targets


def predicted_fields(receipt):
    result = {}
    for field in ("merchant", "date", "subtotal", "tax", "total"):
        value = getattr(receipt, field).value
        result[field] = str(value) if value is not None else None
    result["line_items"] = [
        {
            "name": (i.name.value or "").strip().casefold(),
            "amount": str(i.amount.value) if i.amount.value is not None else None,
        }
        for i in receipt.line_items
    ]
    return result


def canonical(value):
    if isinstance(value, list):
        return [(i["name"], canonical(i["amount"])) for i in value]
    if value is None:
        return None
    try:
        return Decimal(value).normalize()
    except Exception:
        return str(value).strip().casefold()


def exact(actual, expected):
    return float(canonical(actual) == canonical(expected))


def deepeval_score(actual, expected):
    # DeepEval custom deterministic metric: no network, API key, or LLM judge.
    from deepeval.metrics import BaseMetric
    from deepeval.test_case import LLMTestCase

    class CordExactMatch(BaseMetric):
        threshold = 1.0

        def measure(self, test_case, *args, **kwargs):
            self.score = float(test_case.actual_output == test_case.expected_output)
            self.success = self.score >= self.threshold
            return self.score

        async def a_measure(self, test_case, *args, **kwargs):
            return self.measure(test_case)

        def is_successful(self):
            return self.success

        @property
        def __name__(self):
            return "CORD deterministic field match"

    case = LLMTestCase(
        input="CORD field",
        actual_output=str(canonical(actual)),
        expected_output=str(canonical(expected)),
    )
    return CordExactMatch().measure(case)


def evaluate(manifest, responses, output=Path("data/evaluation.json")):
    grouped = defaultdict(list)
    by_id = {row["id"]: row for row in manifest["receipts"]}
    for receipt_id, response in responses:
        if response.get("origin") != "anthropic_live":
            raise ValueError("Refusing non-live responses in evaluation")
        grouped[(response["model"], response["prompt_version"])].append((receipt_id, response))
    results = []
    for (model, prompt), rows in grouped.items():
        if len({rid for rid, _ in rows}) != len(rows):
            raise ValueError("Duplicate receipt/variant")
        counts = {f: {"eligible": 0, "correct": 0, "deepeval_correct": 0} for f in FIELDS}
        failures = 0
        for rid, response in rows:
            truth = cord_targets(by_id[rid]["labels"])
            prediction = {}
            if response.get("receipt"):
                prediction = predicted_fields(Receipt.model_validate(response["receipt"]))
            else:
                failures += 1
            for field, target in truth.items():
                bucket = counts[field]
                bucket["eligible"] += 1
                bucket["correct"] += exact(prediction.get(field), target)
                bucket["deepeval_correct"] += deepeval_score(prediction.get(field), target)
        for bucket in counts.values():
            bucket["accuracy"] = (
                bucket["correct"] / bucket["eligible"] if bucket["eligible"] else None
            )
        results.append(
            {
                "model": model,
                "prompt_version": prompt,
                "receipts": len(rows),
                "response_failures": failures,
                "fields": counts,
                "cost_usd": sum(r["cost_usd"] for _, r in rows),
                "mean_latency_s": sum(r["latency_s"] for _, r in rows) / len(rows),
            }
        )
    payload = {
        "dataset_revision": manifest["revision"],
        "seed": manifest["seed"],
        "split": manifest["split"],
        "sample_size": len(by_id),
        "results": results,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2))
    return payload
