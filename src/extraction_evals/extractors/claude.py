"""Claude with structured outputs: the response is validated against InvoiceExtraction by the SDK."""

import logging
from typing import Any

from extraction_evals.extractors.prompt import user_message
from extraction_evals.schema import InvoiceExtraction, empty_extraction

DEFAULT_MODEL = "claude-opus-5-5"
MAX_TOKENS = 16000

log = logging.getLogger(__name__)


class ClaudeExtractor:
    def __init__(self, model: str = DEFAULT_MODEL, client: Any | None = None) -> None:
        if client is None:
            import anthropic  # optional dependency: pip install "llm-extraction-evals[claude]"

            client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY or an `ant auth login` profile
        self.client = client
        self.model = model
        self.name = f"claude:{model}"

    def extract(self, document_id: str, text: str) -> InvoiceExtraction:
        import anthropic

        try:
            response = self.client.messages.parse(
                model=self.model,
                max_tokens=MAX_TOKENS,
                messages=[{"role": "user", "content": user_message(text)}],
                output_format=InvoiceExtraction,
            )
        except anthropic.APIStatusError as error:
            log.error("Claude failed on %s: %s (request %s)", document_id, error.message, error.request_id)
            return empty_extraction()
        except anthropic.APIConnectionError as error:
            log.error("Claude unreachable on %s: %s", document_id, error)
            return empty_extraction()

        if response.stop_reason in ("refusal", "max_tokens") or response.parsed_output is None:
            log.warning("No usable output for %s (stop_reason=%s)", document_id, response.stop_reason)
            return empty_extraction()
        return response.parsed_output
