"""Side-by-side Markdown tables for one or more scored runs."""

from extraction_evals.schema import FIELDS
from extraction_evals.scoring import Summary


def pct(share: float) -> str:
    return f"{share * 100:.1f}%"


def to_markdown(summaries: list[Summary]) -> str:
    header = "| | " + " | ".join(f"`{s.extractor}`" for s in summaries) + " |"
    divider = "|---|" + "---:|" * len(summaries)
    rows = [
        ("**Field accuracy (all fields)**", [pct(s.overall_field_accuracy) for s in summaries]),
        ("Documents fully correct", [pct(s.document_accuracy) for s in summaries]),
        ("Values backed by exact evidence", [pct(s.grounded_rate) for s in summaries]),
        ("Auto-accepted (no review)", [pct(s.auto_accept_rate) for s in summaries]),
        ("**Auto-accepted that are fully correct**", [pct(s.auto_accepted_accuracy) for s in summaries]),
        ("Wrong documents caught by review", [pct(s.errors_sent_to_review) for s in summaries]),
    ]
    rows += [(f"`{field}`", [pct(s.field_accuracy[field]) for s in summaries]) for field in FIELDS]
    layouts = sorted({layout for s in summaries for layout in s.layout_accuracy})
    rows += [
        (f"Layout `{layout}` fully correct", [pct(s.layout_accuracy.get(layout, 0.0)) for s in summaries])
        for layout in layouts
    ]
    body = [f"| {label} | " + " | ".join(values) + " |" for label, values in rows]
    documents = summaries[0].documents if summaries else 0
    return "\n".join([f"Scored on {documents} documents.", "", header, divider, *body]) + "\n"
