"""Mock provider responses are synthetic; these tests never contact Anthropic."""

import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from receipt_pipeline.extract import Extractor
from receipt_pipeline.synthetic import receipt_dict


def provider(monkeypatch, tmp_path):
    import anthropic

    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("ANTHROPIC_API_KEY=synthetic-test-key\n")
    image = tmp_path / "synthetic.png"
    image.write_bytes(b"synthetic image")
    usage = Mock(input_tokens=100, output_tokens=200)
    usage.model_dump.return_value = {"input_tokens": 100, "output_tokens": 200}
    response = SimpleNamespace(
        usage=usage,
        stop_reason="end_turn",
        content=[SimpleNamespace(type="text", text=json.dumps(receipt_dict()))],
    )
    client = Mock()
    client.messages.count_tokens.return_value = SimpleNamespace(input_tokens=100)
    client.messages.create.return_value = response
    monkeypatch.setattr(anthropic, "Anthropic", Mock(return_value=client))
    return client, image, response


def test_paid_response_cached_and_metered(tmp_path, monkeypatch):
    client, image, _ = provider(monkeypatch, tmp_path)
    extractor = Extractor(tmp_path / "cache", live=True)
    first = extractor.run(image, "claude-haiku-5-5", "v1")
    assert first == extractor.run(image, "claude-haiku-5-5", "v1")
    assert client.messages.create.call_count == 1
    assert first["receipt"]["total"]["model"] == "claude-haiku-5-5"
    ledger = json.loads((extractor.root / "spend.json").read_text())
    assert ledger[0]["status"] == "billed"
    assert ledger[0]["charged_or_reserved_usd"] == pytest.approx(0.00011)


def test_budget_stops_before_paid_request(tmp_path, monkeypatch):
    client, image, _ = provider(monkeypatch, tmp_path)
    extractor = Extractor(tmp_path / "cache", live=True)
    (extractor.root / "spend.json").write_text(json.dumps([{"charged_or_reserved_usd": 5}]))
    with pytest.raises(RuntimeError, match="Budget cap"):
        extractor.run(image, "claude-sonnet-5-5", "v2")
    client.messages.create.assert_not_called()


def test_uncertain_failure_reserves_spend(tmp_path, monkeypatch):
    client, image, _ = provider(monkeypatch, tmp_path)
    client.messages.create.side_effect = TimeoutError("synthetic timeout")
    extractor = Extractor(tmp_path / "cache", live=True)
    with pytest.raises(TimeoutError):
        extractor.run(image, "claude-sonnet-5-5", "v2")
    ledger = json.loads((extractor.root / "spend.json").read_text())
    assert ledger[0]["status"] == "reserved"
    assert ledger[0]["charged_or_reserved_usd"] > 0


def test_malformed_response_is_cached_for_review(tmp_path, monkeypatch):
    client, image, response = provider(monkeypatch, tmp_path)
    response.content[0].text = "{invalid json"
    extractor = Extractor(tmp_path / "cache", live=True)
    result = extractor.run(image, "claude-haiku-5-5", "v1")
    assert result["error"].startswith("invalid_response:")
    assert result == extractor.run(image, "claude-haiku-5-5", "v1")
    assert client.messages.create.call_count == 1
