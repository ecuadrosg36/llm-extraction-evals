"""The LLM adapters are tested with fake clients: no keys, no network, no cost."""

from types import SimpleNamespace

import anthropic
import httpx2
import pytest
from google.genai import errors

from extraction_evals.extractors.claude import DEFAULT_MODEL, ClaudeExtractor
from extraction_evals.extractors.gemini import GeminiExtractor
from extraction_evals.extractors.prompt import user_message
from extraction_evals.extractors.replay import ReplayExtractor
from extraction_evals.runs import load_run, save_run
from extraction_evals.schema import FIELDS, Extracted, InvoiceExtraction

GOOD = InvoiceExtraction(**{f: Extracted(value="x", evidence="x") for f in FIELDS})
REQUEST = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")


class FakeClaude:
    def __init__(self, result=None, error: Exception | None = None) -> None:
        self.result, self.error, self.calls = result, error, []
        self.messages = self

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.result


def test_claude_sends_the_document_and_schema() -> None:
    fake = FakeClaude(SimpleNamespace(stop_reason="end_turn", parsed_output=GOOD))

    result = ClaudeExtractor(client=fake).extract("doc-1", "INVOICE 1")

    call = fake.calls[0]
    assert result == GOOD
    assert call["model"] == DEFAULT_MODEL == "claude-opus-5-5"
    assert call["output_format"] is InvoiceExtraction
    assert "<document>\nINVOICE 1\n</document>" in call["messages"][0]["content"]


@pytest.mark.parametrize("stop_reason", ["refusal", "max_tokens"])
def test_claude_unusable_output_becomes_empty(stop_reason) -> None:
    fake = FakeClaude(SimpleNamespace(stop_reason=stop_reason, parsed_output=None))

    assert ClaudeExtractor(client=fake).extract("d", "t").vendor_name.value is None


@pytest.mark.parametrize(
    "error",
    [
        anthropic.BadRequestError("bad", response=httpx2.Response(400, request=REQUEST), body=None),
        anthropic.APIConnectionError(request=REQUEST),
    ],
    ids=["status-error", "connection-error"],
)
def test_claude_errors_do_not_stop_the_run(error, caplog) -> None:
    result = ClaudeExtractor(client=FakeClaude(error=error)).extract("doc-9", "t")

    assert result.total_amount.value is None
    assert "doc-9" in caplog.text


class FakeGemini:
    def __init__(self, parsed=None, error: Exception | None = None) -> None:
        self.parsed, self.error, self.calls = parsed, error, []
        self.models = self

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return SimpleNamespace(parsed=self.parsed)


def test_gemini_uses_the_schema() -> None:
    fake = FakeGemini(parsed=GOOD)

    result = GeminiExtractor("some-model", client=fake).extract("d", "INVOICE 2")

    assert result == GOOD
    assert fake.calls[0]["config"]["response_schema"] is InvoiceExtraction
    assert fake.calls[0]["contents"] == user_message("INVOICE 2")


def test_gemini_bad_output_and_errors_become_empty(caplog) -> None:
    assert GeminiExtractor("m", client=FakeGemini(parsed=None)).extract("d", "t").currency.value is None
    error = errors.APIError(429, {"error": {"message": "slow down", "status": "RESOURCE_EXHAUSTED"}})

    assert GeminiExtractor("m", client=FakeGemini(error=error)).extract("doc-7", "t").currency.value is None
    assert "doc-7" in caplog.text


def test_runs_round_trip_and_replay(tmp_path) -> None:
    path = tmp_path / "run.jsonl"
    save_run(path, "claude:test", {"a": GOOD})

    assert load_run(path) == ("claude:test", {"a": GOOD})
    replay = ReplayExtractor(path)
    assert replay.name == "claude:test"
    assert replay.extract("a", "") == GOOD
    assert replay.extract("missing", "").vendor_name.value is None


def test_run_file_without_header_is_rejected(tmp_path) -> None:
    path = tmp_path / "bad.jsonl"
    path.write_text('{"id": "a"}\n')

    with pytest.raises(ValueError, match="not a run file"):
        load_run(path)
