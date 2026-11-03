"""Extractors share one method: extract(text) -> InvoiceExtraction."""

from typing import Protocol

from extraction_evals.schema import InvoiceExtraction


class Extractor(Protocol):
    name: str

    def extract(self, document_id: str, text: str) -> InvoiceExtraction: ...
