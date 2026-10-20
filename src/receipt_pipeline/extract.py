"""Content-addressed responses, durable spend reservation, no implicit live calls."""

import base64
import fcntl
import hashlib
import json
import time
from datetime import UTC, datetime
from pathlib import Path

from dotenv import dotenv_values

from receipt_pipeline.schema import Receipt

RATES = {"claude-haiku-5-5": (0.10, 0.50), "claude-sonnet-5-5": (2.0, 10.0)}
PROMPTS = {
    "v1": (
        "Extract only visible receipt fields. Return null when absent. Never invent a date or tax."
    ),
    "v2": "Read receipt row by row. Distinguish extended amounts from unit prices. "
    "Transcribe visible fields, then check arithmetic without altering the source. "
    "Return null for missing fields; never infer missing tax or date.",
}
MAX_OUTPUT = 8192
# Conservative single-image input envelope; fail closed if a request would exceed this.
MAX_INPUT = 32000
BUDGET = 5.0


def request_key(image: bytes, model: str, prompt: str):
    body = {
        "image": hashlib.sha256(image).hexdigest(),
        "model": model,
        "prompt": PROMPTS[prompt],
        "version": prompt,
        "schema": Receipt.model_json_schema(),
        "max_tokens": MAX_OUTPUT,
    }
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()


def estimate(model, n=1):
    inp, out = RATES[model]
    return n * (MAX_INPUT * inp + MAX_OUTPUT * out) / 1_000_000


def atomic_json(path, payload):
    temporary = path.with_suffix(".tmp")
    with temporary.open("w") as handle:
        handle.write(json.dumps(payload, indent=2))
        handle.flush()
        import os

        os.fsync(handle.fileno())
    temporary.replace(path)


class Extractor:
    def __init__(self, root=Path("data"), live=False):
        self.root = root
        self.live = live
        self.cache = root / "responses"
        self.cache.mkdir(parents=True, exist_ok=True)

    def run(self, image_path: Path, model: str, prompt: str):
        image = image_path.read_bytes()
        key = request_key(image, model, prompt)
        path = self.cache / f"{key}.json"
        # Single shared lock covers both spend ledger and response writes across processes.
        with (self.root / "spend.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if path.exists():
                return json.loads(path.read_text())
            if not self.live:
                raise RuntimeError(f"Cache miss {key}; live calls disabled")
            key_value = dotenv_values(".env").get("ANTHROPIC_API_KEY")
            if not key_value:
                raise RuntimeError("Missing ANTHROPIC_API_KEY in gitignored .env")
            from anthropic import Anthropic, transform_schema

            client = Anthropic(api_key=key_value, max_retries=0, timeout=90)
            content = [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": base64.b64encode(image).decode(),
                    },
                },
                {
                    "type": "text",
                    "text": PROMPTS[prompt] + " Use normalized evidence regions. "
                    f"Set every field model={model}, prompt_version={prompt}. "
                    "Amounts are numeric currency units, excluding grouping separators.",
                },
            ]
            schema = {"format": {"type": "json_schema", "schema": transform_schema(Receipt)}}
            # Counting is unbilled, but still explicit-live only.
            count = client.messages.count_tokens(
                model=model,
                messages=[{"role": "user", "content": content}],
                output_config=schema,
            ).input_tokens
            if count > MAX_INPUT:
                raise RuntimeError("Input exceeds reserved cost envelope")
            ledger_path = self.root / "spend.json"
            ledger = json.loads(ledger_path.read_text()) if ledger_path.exists() else []
            reservation = estimate(model)
            if sum(x["charged_or_reserved_usd"] for x in ledger) + reservation > BUDGET:
                raise RuntimeError("Budget cap reached; stop and ask before increasing spending")
            entry = {
                "key": key,
                "model": model,
                "charged_or_reserved_usd": reservation,
                "status": "reserved",
            }
            ledger.append(entry)
            atomic_json(ledger_path, ledger)
            start = time.monotonic()
            # On timeout/crash reserve stays charged; no automatic paid retries.
            response = client.messages.create(
                model=model,
                max_tokens=MAX_OUTPUT,
                messages=[{"role": "user", "content": content}],
                output_config=schema,
            )
            elapsed = time.monotonic() - start
            usage = response.usage
            inp, out = RATES[model]
            cost = (usage.input_tokens * inp + usage.output_tokens * out) / 1_000_000
            entry.update(
                charged_or_reserved_usd=cost,
                status="billed",
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
            )
            atomic_json(ledger_path, ledger)
            text = "".join(block.text for block in response.content if block.type == "text")
            result = {
                "key": key,
                "model": model,
                "prompt_version": prompt,
                "receipt": None,
                "error": None,
                "raw_text": text,
                "latency_s": elapsed,
                "cost_usd": cost,
                "usage": usage.model_dump(),
                "origin": "anthropic_live",
                "acquired_at": datetime.now(UTC).isoformat(),
                "provider_request_id": getattr(response, "id", None),
                "counted_input_tokens": count,
            }
            try:
                if response.stop_reason != "end_turn":
                    raise ValueError(f"stop_reason:{response.stop_reason}")
                parsed = Receipt.model_validate_json(text)
                # Provenance comes from request, not model claims.
                for _, obs in parsed.observations():
                    obs.model, obs.prompt_version = model, prompt
                result["receipt"] = parsed.model_dump(mode="json")
            except ValueError as exc:
                result["error"] = f"invalid_response:{type(exc).__name__}"
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(result, indent=2))
            tmp.replace(path)
            return result
