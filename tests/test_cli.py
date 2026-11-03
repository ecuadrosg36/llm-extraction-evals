from pathlib import Path

import pytest

from extraction_evals import cli
from extraction_evals.dataset import DOCS_PER_LAYOUT, LAYOUTS, load

REPO = Path(__file__).parent.parent


def test_generate_run_score_and_gate(tmp_path, capsys) -> None:
    data, run = tmp_path / "invoices.jsonl", tmp_path / "baseline.jsonl"

    assert cli.main(["--data", str(data), "generate"]) == 0
    assert len(load(data)) == len(LAYOUTS) * DOCS_PER_LAYOUT

    assert cli.main(["--data", str(data), "run", "--extractor", "baseline", "--out", str(run)]) == 0
    assert "`baseline-regex`" in capsys.readouterr().out

    assert cli.main(["--data", str(data), "score", str(run), str(run)]) == 0
    assert capsys.readouterr().out.count("`baseline-regex`") == 2

    assert cli.main(["--data", str(data), "gate", str(run), "--min-accuracy", "0.5"]) == cli.EXIT_OK
    assert cli.main(["--data", str(data), "gate", str(run), "--min-accuracy", "0.99"]) == cli.EXIT_BELOW_BAR
    assert "FAIL" in capsys.readouterr().out


def test_gemini_needs_an_explicit_model() -> None:
    with pytest.raises(SystemExit, match="--model is required"):
        cli.make_extractor("gemini", None)


def test_committed_data_matches_the_generator() -> None:
    """data/invoices.jsonl is generated; if this fails, run `evals generate`."""
    from extraction_evals.dataset import generate

    assert load(REPO / "data" / "invoices.jsonl") == generate()
