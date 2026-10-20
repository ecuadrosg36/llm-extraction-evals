# Engineering decisions

## Grain and lineage

`raw.receipts`: one receipt ID, image reference, SHA-256, source revision and
original CORD labels. `raw.extractions`: one image/model/prompt/schema content
hash with response, usage, original latency/cost, validation status and reasons.
`raw.review_queue`: one pending/resolved case per extraction. `raw.corrections`:
append-only label versions with reviewer, action and timestamp. dbt chooses the
latest correction per extraction, then emits one receipt fact and ordered line
item facts. Source annotations and human labels are never conflated.

Field provenance lives inside typed JSONB response/label documents. This preserves
evidence even for quarantined records. Model/prompt provenance is stamped by the
caller after response validation. Text spans and normalized bounding rectangles
are model claims tied to the source image, not verified OCR citations. No claim
of evidence grounding accuracy is made without human annotation.

## Reproducibility and safety

The download script pins a Hugging Face dataset commit and a local seeded index
selection. The public manifest contains indices and image hashes only. PNG images
and original labels are downloaded into ignored `data/`. Extraction checks hashes
before using images. Changing prompt contents, model, output schema or token limit
changes the cache key. Existing cache entries replay without keys or paid calls.

The shared file lock serializes cache writes and budget reservations on this
single-machine runner. A durable reservation is written before the paid request;
actual usage replaces it after response. Automatic provider retries are disabled.
An uncertain timeout remains reserved, so rerunning cannot quietly overspend.
Ledger writes are atomic with file fsync. Multi-host workers would require a
transactional centralized budget ledger and object-store cache, not file locks.
The ledger is local to `data/`: use one root for all authorized live work and never
reset it or start another root to evade the project cap.

No provider key is loaded from the process environment. Only `.env` is read for
`ANTHROPIC_API_KEY`; `.env.example` contains no credential. CI uses synthetic data
and never invokes live extraction, dataset download, or an LLM judge. Telemetry
for dbt/DeepEval is disabled. Local tests disable unrelated auto-loaded pytest
plugins for predictable offline behavior.

## Validation and review

Amounts use Decimal; grouping separators are removed from CORD labels with an
explicit Indonesian currency parser. Extraction values are numeric currency
units. Item amounts mean extended totals. Equality is exact in native units;
no floating-point tolerance hides discrepancies. Dates must parse as ISO dates.
Absent tax stays absent; service charges and discounts currently cause review
when the required equalities do not hold. This conservative contract is a known
coverage limitation, not evidence of model error by itself.

All scalar fields carry evidence and confidence. Missing values, invalid regions,
negative amounts, low confidence and sum/date failures are recorded as reasons.
Malformed structured responses are cached with raw text and metering and sent to
review. Human acceptance can override low self-reported confidence but cannot
bypass missing values, source evidence, arithmetic or date checks. Corrections
preserve original model evidence unless explicitly edited by the reviewer. Reviewer
identity is asserted locally; authentication/RBAC is future work.

## Orchestration and operations

Dagster assets express ingest → extract → validate → dbt → evals. A blocking fixed
sample asset check verifies size; the quality asset check exposes review workload.
Rejected rows remain queryable and do not enter the warehouse until corrected.
The evaluation asset reads every model response, including rejected records.

Python transactions make metadata ingestion idempotent; extraction hashes make
response storage idempotent. Review queue updates preserve resolution status.
Schema creation is bootstrap DDL rather than a migration framework; production
rollout would add versioned migrations, retention policies, secret management,
centralized observability and authenticated review. Compose credentials are
local development defaults with a loopback-bound port.

## Evaluation interpretation

`docs/results.md` is the public evidence ledger. No synthetic payload is accepted
by the live evaluation aggregator. DeepEval is intentionally a deterministic
custom metric, avoiding judge cost and evaluator variability. It verifies the
same match rule as the standalone comparator, not a second estimate of quality.
Scores must show eligible denominators and failed-output counts. Missing labels
are not negative labels; merchant/date cannot be benchmarked on this dataset alone.
The sampled train split supports a reproducible portfolio demonstration, not a
claim of held-out generalization. Prompt changes must be followed by new cache keys
and results, and tuning against this sample must be disclosed.
