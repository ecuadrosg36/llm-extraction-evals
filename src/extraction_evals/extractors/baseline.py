"""Regex baseline: what you get without an LLM. It sets the bar the models have to beat.

It is deliberately simple: first match wins. That is exactly how it falls into the traps in the dataset.
"""

import re
from datetime import date

from extraction_evals.dataset import MONTHS_EN
from extraction_evals.normalize import amount, currency
from extraction_evals.schema import Extracted, InvoiceExtraction

PATTERNS = {
    "invoice_number": r"(?:INVOICE|FACTURA ELECTRÓNICA|Folio:|invoice no\.)\s*([A-Z0-9-]+)",
    "vendor_tax_id": r"(?:EIN|RUC|RFC:|NIT)\s*([0-9A-Z.-]{8,})",
    "total_amount": r"(?:Total due:|Importe total:|Total:|amount of)\s*(?:\$|S/|MXN|COP)?\s*([0-9.,]+)",
    "currency": r"(\$|S/|MXN|COP)",
    "vendor_name": r"(?:From:|Emisor:|from)\s+(.+?)(?:\s{2}| \(|\n)",
}
DATE_PATTERNS = (
    (r"(\d{4}-\d{2}-\d{2})", lambda m: m.group(1)),
    (r"(\d{2})/(\d{2})/(\d{4})", lambda m: f"{m.group(3)}-{m.group(2)}-{m.group(1)}"),
    (r"([A-Z][a-z]+) (\d{1,2}), (\d{4})", lambda m: _month_date(m.group(3), m.group(1), m.group(2))),
)


def _month_date(year: str, month: str, day: str) -> str | None:
    months = [m.lower() for m in MONTHS_EN]
    if month.lower() not in months:
        return None
    return date(int(year), months.index(month.lower()) + 1, int(day)).isoformat()


def _find(pattern: str, text: str) -> Extracted:
    match = re.search(pattern, text)
    return (
        Extracted(value=match.group(1).strip(), evidence=match.group(0))
        if match
        else Extracted(value=None, evidence=None)
    )


def _dates(text: str) -> list[Extracted]:
    found = []
    for pattern, to_iso in DATE_PATTERNS:
        for match in re.finditer(pattern, text):
            found.append((match.start(), Extracted(value=to_iso(match), evidence=match.group(0))))
    return [extracted for _, extracted in sorted(found, key=lambda pair: pair[0])]


class BaselineExtractor:
    name = "baseline-regex"

    def extract(self, document_id: str, text: str) -> InvoiceExtraction:
        fields = {name: _find(pattern, text) for name, pattern in PATTERNS.items()}
        total = fields["total_amount"]
        fields["total_amount"] = Extracted(
            value=str(amount(total.value)) if total.value else None, evidence=total.evidence
        )
        symbol = fields["currency"]
        fields["currency"] = Extracted(value=currency(symbol.value), evidence=symbol.evidence)
        dates = _dates(text)
        none = Extracted(value=None, evidence=None)
        fields["issue_date"] = dates[0] if dates else none
        fields["due_date"] = dates[1] if len(dates) > 1 else none
        return InvoiceExtraction(**fields)
