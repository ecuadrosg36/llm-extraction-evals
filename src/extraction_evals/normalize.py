"""Turn the many ways a value can be written into one form, so scoring compares meaning, not formatting."""

import re
from datetime import date
from decimal import Decimal, InvalidOperation

AMOUNT_TOLERANCE = Decimal("0.005")
CURRENCY_SYMBOLS = {"S/": "PEN", "US$": "USD", "$": "USD", "€": "EUR"}


def text(value: str | None) -> str | None:
    """Case and spacing don't matter for names and IDs."""
    if value is None:
        return None
    cleaned = re.sub(r"\s+", " ", value).strip().upper()
    return cleaned or None


def tax_id(value: str | None) -> str | None:
    """RUC 20-123... and 20123... are the same ID."""
    cleaned = text(value)
    return re.sub(r"[^0-9A-Z]", "", cleaned) if cleaned else None


def iso_date(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(value.strip()).isoformat()
    except ValueError:
        return None


def amount(value: str | None) -> Decimal | None:
    """Accepts 1234.5, 1,234.50 and 1.234,50."""
    if value is None:
        return None
    digits = re.sub(r"[^0-9,.\-]", "", value)
    if "," in digits and "." in digits:
        digits = (
            digits.replace(".", "").replace(",", ".")
            if digits.rfind(",") > digits.rfind(".")
            else digits.replace(",", "")
        )
    elif digits.count(".") > 1 or re.fullmatch(r"-?\d{1,3}\.\d{3}", digits):
        digits = digits.replace(".", "")  # 3.450.000 or 450.000: dots group thousands
    elif "," in digits:
        whole, _, frac = digits.rpartition(",")
        digits = f"{whole}.{frac}" if len(frac) == 2 else digits.replace(",", "")
    try:
        return Decimal(digits)
    except InvalidOperation:
        return None


def currency(value: str | None) -> str | None:
    cleaned = text(value)
    if cleaned is None:
        return None
    return CURRENCY_SYMBOLS.get(cleaned, cleaned)


def same(field: str, predicted: str | None, expected: str | None) -> bool:
    """True when the prediction means the same as the gold label."""
    if field == "total_amount":
        a, b = amount(predicted), amount(expected)
        return a == b if a is None or b is None else abs(a - b) <= AMOUNT_TOLERANCE
    normalizer = {"issue_date": iso_date, "due_date": iso_date, "currency": currency, "vendor_tax_id": tax_id}
    fn = normalizer.get(field, text)
    return fn(predicted) == fn(expected)
