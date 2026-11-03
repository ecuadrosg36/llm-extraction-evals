"""What an extractor must return: a value and the exact text it came from, for every field."""

from pydantic import BaseModel, Field

FIELDS = ("vendor_name", "vendor_tax_id", "invoice_number", "issue_date", "due_date", "currency", "total_amount")


class Extracted(BaseModel):
    value: str | None = Field(description="Normalized value, or null when the document does not contain it.")
    evidence: str | None = Field(description="Exact text copied from the document that supports the value.")


class InvoiceExtraction(BaseModel):
    vendor_name: Extracted = Field(description="The company that issued the invoice (the seller), not the customer.")
    vendor_tax_id: Extracted = Field(description="The seller's tax ID (RUC, NIT, RFC, EIN), not the customer's.")
    invoice_number: Extracted
    issue_date: Extracted = Field(description="ISO date YYYY-MM-DD.")
    due_date: Extracted = Field(description="ISO date YYYY-MM-DD, or null if the invoice has none.")
    currency: Extracted = Field(description="ISO 4217 code, e.g. PEN, USD, MXN, COP.")
    total_amount: Extracted = Field(description="Amount due including tax, as a plain number with a dot: 1234.50.")


def empty_extraction() -> InvoiceExtraction:
    """What a failed call returns, so one bad document never stops a whole run."""
    return InvoiceExtraction(**{name: Extracted(value=None, evidence=None) for name in FIELDS})
