"""Re-score a saved run without calling any API. CI uses this, so it never needs keys or spends money."""

from pathlib import Path

from extraction_evals.runs import load_run
from extraction_evals.schema import InvoiceExtraction, empty_extraction


class ReplayExtractor:
    def __init__(self, run_file: Path) -> None:
        self.name, self._predictions = load_run(run_file)

    def extract(self, document_id: str, text: str) -> InvoiceExtraction:
        return self._predictions.get(document_id, empty_extraction())
