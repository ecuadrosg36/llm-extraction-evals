"""A run is the raw output of one extractor on the dataset, saved as JSON lines so it can be re-scored later."""

import json
from pathlib import Path

from extraction_evals.schema import InvoiceExtraction


def save_run(path: Path, extractor_name: str, predictions: dict[str, InvoiceExtraction]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as out:
        out.write(json.dumps({"extractor": extractor_name}) + "\n")
        for doc_id, prediction in predictions.items():
            out.write(json.dumps({"id": doc_id, "prediction": prediction.model_dump()}, ensure_ascii=False) + "\n")


def load_run(path: Path) -> tuple[str, dict[str, InvoiceExtraction]]:
    with path.open(encoding="utf-8") as f:
        header, *rows = [json.loads(line) for line in f if line.strip()]
    if "extractor" not in header:
        raise ValueError(f"{path} is not a run file: the first line must name the extractor.")
    return header["extractor"], {row["id"]: InvoiceExtraction.model_validate(row["prediction"]) for row in rows}
