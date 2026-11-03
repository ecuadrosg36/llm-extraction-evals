"""Gemini with a response schema: the SDK parses the JSON into InvoiceExtraction."""

import logging
from typing import Any

from extraction_evals.extractors.prompt import user_message
from extraction_evals.schema import InvoiceExtraction, empty_extraction

log = logging.getLogger(__name__)


class GeminiExtractor:
    def __init__(self, model: str, client: Any | None = None) -> None:
        if client is None:
            from google import genai  # optional dependency: pip install "llm-extraction-evals[gemini]"

            client = genai.Client()  # reads GEMINI_API_KEY or GOOGLE_API_KEY
        self.client = client
        self.model = model
        self.name = f"gemini:{model}"

    def extract(self, document_id: str, text: str) -> InvoiceExtraction:
        from google.genai import errors

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=user_message(text),
                config={"response_mime_type": "application/json", "response_schema": InvoiceExtraction},
            )
        except errors.APIError as error:
            log.error("Gemini failed on %s: %s %s", document_id, error.code, error.message)
            return empty_extraction()

        parsed = response.parsed
        if not isinstance(parsed, InvoiceExtraction):
            log.warning("No usable output for %s", document_id)
            return empty_extraction()
        return parsed
