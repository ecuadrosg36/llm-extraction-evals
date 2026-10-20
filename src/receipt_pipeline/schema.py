from datetime import date
from decimal import Decimal, InvalidOperation
from typing import TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    span: str = Field(description="Verbatim visible text; empty only when absent")
    region: list[float] = Field(
        description="Normalized [left, top, right, bottom], empty if not localized"
    )


class Observed[T](BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: T | None
    evidence: Evidence
    confidence: float = Field(ge=0, le=1)
    model: str
    prompt_version: str


class LineItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Observed[str]
    quantity: Observed[Decimal]
    amount: Observed[Decimal] = Field(description="Extended line total, not unit price")


class Receipt(BaseModel):
    model_config = ConfigDict(extra="forbid")
    merchant: Observed[str]
    date: Observed[str] = Field(description="ISO YYYY-MM-DD when unambiguous; null if absent")
    line_items: list[LineItem]
    subtotal: Observed[Decimal]
    tax: Observed[Decimal]
    total: Observed[Decimal]

    def observations(self):
        for field in ("merchant", "date", "subtotal", "tax", "total"):
            yield field, getattr(self, field)
        for i, item in enumerate(self.line_items):
            for field in ("name", "quantity", "amount"):
                yield f"line_items.{i}.{field}", getattr(item, field)


def money(text: str) -> Decimal:
    """CORD Indonesian amounts: grouping dots/commas, optionally two decimal places.

    Reject ambiguous decimal conventions rather than silently guessing cents.
    """
    text = text.strip().replace("Rp", "").replace(" ", "")
    if not text:
        raise ValueError("empty money")
    if text.count(",") == 1 and len(text.rsplit(",", 1)[1]) == 2:
        text = text.replace(".", "").replace(",", ".")
    elif text.count(".") == 1 and len(text.rsplit(".", 1)[1]) == 2:
        text = text.replace(",", "")
    else:
        text = text.replace(".", "").replace(",", "")
    try:
        value = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError("invalid money") from exc
    if not value.is_finite():
        raise ValueError("nonfinite money")
    return value


def validate(receipt: Receipt, threshold: float = 0.8) -> list[str]:
    reasons = []
    try:
        date.fromisoformat(receipt.date.value or "")
    except ValueError:
        reasons.append("unparseable_date")
    amounts = [item.amount.value for item in receipt.line_items]
    if not amounts or any(x is None for x in amounts) or receipt.subtotal.value is None:
        reasons.append("missing_item_or_subtotal")
    elif sum(amounts, Decimal(0)) != receipt.subtotal.value:
        reasons.append("items_sum_ne_subtotal")
    if any(x.value is None for x in (receipt.subtotal, receipt.tax, receipt.total)):
        reasons.append("missing_totals")
    elif receipt.subtotal.value + receipt.tax.value != receipt.total.value:
        reasons.append("subtotal_plus_tax_ne_total")
    for path, obs in receipt.observations():
        if obs.value is None or obs.confidence < threshold:
            reasons.append(f"low_confidence:{path}")
        if obs.value is not None and not obs.evidence.span and not obs.evidence.region:
            reasons.append(f"missing_evidence:{path}")
        box = obs.evidence.region
        if box and (
            len(box) != 4
            or not all(0 <= x <= 1 for x in box)
            or box[0] >= box[2]
            or box[1] >= box[3]
        ):
            reasons.append(f"invalid_region:{path}")
        if isinstance(obs.value, Decimal) and (not obs.value.is_finite() or obs.value < 0):
            reasons.append(f"invalid_amount:{path}")
        if path.endswith(".quantity") and obs.value is not None and obs.value <= 0:
            reasons.append(f"invalid_quantity:{path}")
    return reasons
