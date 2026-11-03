"""Score every field, check its evidence, and decide which documents a person must review.

A field is *grounded* when its evidence is copied word for word from the document. A document is
*auto-accepted* only when every required field has a value and every value is grounded. Everything else goes
to a human. The number that matters most is how often auto-accepted documents are fully correct.
"""

import re
from dataclasses import dataclass

from extraction_evals.dataset import Document
from extraction_evals.normalize import same
from extraction_evals.schema import FIELDS, InvoiceExtraction, empty_extraction

OPTIONAL_FIELDS = frozenset({"due_date"})


@dataclass(frozen=True)
class DocScore:
    id: str
    layout: str
    correct: dict[str, bool]
    grounded: dict[str, bool]

    @property
    def all_correct(self) -> bool:
        return all(self.correct.values())

    @property
    def auto_accepted(self) -> bool:
        return all(self.grounded.values())


@dataclass(frozen=True)
class Summary:
    extractor: str
    documents: int
    field_accuracy: dict[str, float]
    grounded_rate: float
    document_accuracy: float
    auto_accept_rate: float
    auto_accepted_accuracy: float
    """Of the documents nobody reviews, the share with every field right."""
    errors_sent_to_review: float
    """Of the documents with any wrong field, the share routed to a person."""
    layout_accuracy: dict[str, float]

    @property
    def overall_field_accuracy(self) -> float:
        return sum(self.field_accuracy.values()) / len(self.field_accuracy)


def _squash(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def is_grounded(field: str, value: str | None, evidence: str | None, text: str) -> bool:
    if value is None:
        return field in OPTIONAL_FIELDS  # a missing required field always needs a person
    return bool(evidence) and _squash(evidence) in _squash(text)


def score_document(doc: Document, prediction: InvoiceExtraction) -> DocScore:
    correct, grounded = {}, {}
    for field in FIELDS:
        extracted = getattr(prediction, field)
        correct[field] = same(field, extracted.value, doc.gold[field])
        grounded[field] = is_grounded(field, extracted.value, extracted.evidence, doc.text)
    return DocScore(doc.id, doc.layout, correct, grounded)


def _share(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def summarize(extractor: str, scores: list[DocScore]) -> Summary:
    accepted = [s for s in scores if s.auto_accepted]
    wrong = [s for s in scores if not s.all_correct]
    layouts = sorted({s.layout for s in scores})
    return Summary(
        extractor=extractor,
        documents=len(scores),
        field_accuracy={f: _share(sum(s.correct[f] for s in scores), len(scores)) for f in FIELDS},
        grounded_rate=_share(sum(sum(s.grounded.values()) for s in scores), len(scores) * len(FIELDS)),
        document_accuracy=_share(sum(s.all_correct for s in scores), len(scores)),
        auto_accept_rate=_share(len(accepted), len(scores)),
        auto_accepted_accuracy=_share(sum(s.all_correct for s in accepted), len(accepted)),
        errors_sent_to_review=_share(sum(not s.auto_accepted for s in wrong), len(wrong)),
        layout_accuracy={
            layout: _share(
                sum(s.all_correct for s in scores if s.layout == layout), sum(s.layout == layout for s in scores)
            )
            for layout in layouts
        },
    )


def score_run(extractor: str, documents: list[Document], predictions: dict[str, InvoiceExtraction]) -> Summary:
    return summarize(extractor, [score_document(d, predictions.get(d.id, empty_extraction())) for d in documents])
