# Results and current limits

Status: **implementation verified; live extraction evaluation pending**. No model
accuracy, live latency, or production-readiness claim is made. Last verified:
2026-10-20. All numerical claims in the README are sourced here.

## Actual live evaluation

| Model | Prompt | Evaluated receipts | Field accuracy | API cost USD | Mean latency |
|---|---|---:|---|---|---|
| claude-haiku-5-5 | v1 | 0 | Pending | Not measured | Not measured |
| claude-haiku-5-5 | v2 | 0 | Pending | Not measured | Not measured |
| claude-sonnet-5-5 | v2 | 0 | Pending | Not measured | Not measured |

Actual paid calls: **0**. Actual spend: **$0**. The gitignored `.env` with
`ANTHROPIC_API_KEY` has not been supplied. Fixture outputs are not live results.

## Actual source-data verification

Downloaded and hash-verified **200** distinct receipts from the CORD-v2 train
split, selected without replacement from **800** rows with seed **20261020**.
Dataset revision: `7f0115a4b758a71d6473b8d085751692da2fef98`.
[Public manifest](sample-manifest.json) records receipt indices and image hashes;
images and full source annotations remain in ignored `data/`.

The adapter found these scoreable labels in the actual downloaded sample:

| Field | Eligible receipts | Policy |
|---|---:|---|
| Merchant | 0 | Not present in CORD-v2 gt_parse; unscored |
| Date | 0 | Not present in CORD-v2 gt_parse; unscored |
| Line items | 197 | Ordered normalized names and extended prices |
| Subtotal | 131 | Explicit subtotal_price only |
| Tax | 87 | Explicit tax_price only; no inferred zero |
| Total | 192 | Explicit total_price only |

These are **label coverage counts, not model accuracy**. Unparseable/ambiguous
label structures are excluded with no inferred truth. Repeated name fragments
are joined with spaces. Line-item quantity is extracted with evidence but is
not included in the current benchmark metric. Merchant/date require independent
human labels; review corrections remain separate from this fixed benchmark.

## Validation completed

- Python **3.12.13** with locked uv dependencies.
- **22 pytest tests passed**, including Postgres review/correction integration,
  synthetic response parsing, arithmetic/date rejection, content cache behavior,
  missing-key handling, budget rejection, timeout reservation, and malformed
  paid-response caching. All provider responses in tests are synthetic mocks.
- dbt build passed **5 models and 17 data tests** against **Postgres 16**, using
  explicitly synthetic CI data. Includes uniqueness, not-null, relationships,
  nonnegative ranges, item/subtotal and subtotal/tax/total reconciliation.
- Ruff passed; Dagster software-defined asset definitions validated.
- `make demo` target: **20 cached receipts**, with **3 variants** per receipt,
  cache-only, target under **5 minutes**. **Not yet timed or demonstrated**:
  genuine response caches are unavailable. Cold sample download is separate.

## Cost plan and stop condition

Official Anthropic docs checked on **2026-10-20**, before any calls:

| Requested model ID | Listed and structured outputs supported | Input USD / million tokens | Output USD / million tokens |
|---|---|---:|---:|
| claude-haiku-5-5 | Yes | 0.10 | 0.50 |
| claude-sonnet-5-5 | Yes | 2.00 | 10.00 |

Haiku rates above apply below **100,000** input tokens. Each request is limited
to an input envelope of **32,000** tokens and **8,192** output tokens. The
conservative full **600-call** reservation estimate is **$32.1024**, not an
actual bill. The same envelope for the initial **60-call** demo warmup is
**$3.21024**. Token counting checks the input envelope before paid requests;
actual usage is metered after each response. The durable ledger keeps uncertain
calls reserved and refuses any request that could exceed the **$5** cap.

This does not authorize the larger estimate. Start with `--limit 20`, inspect
the actual ledger, then continue only within the cap. Stop and ask before any
budget increase. Never delete the ledger to bypass it. Disk cache hits make no
provider calls; they retain original acquisition cost/latency in evaluation.

Sources: [models](https://platform.claude.com/docs/en/models/overview),
[pricing](https://platform.claude.com/docs/en/about-claude/pricing),
[structured outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs).

## Evaluation protocol

The same fixed sample is used across variants; labels never enter prompts.
Evaluate all responses, including rejected and malformed outputs, to avoid
survivorship bias. Failed outputs count as incorrect wherever truth exists.
Exact match canonicalizes numeric amounts with Decimal, trims/case-folds names,
and preserves item order. DeepEval uses a deterministic custom BaseMetric with
the same normalization; it is a harness check, not an independent LLM judge.
No external judge or API is used by pytest, dbt, or CI. No confidence calibration
claim is made: model confidence is self-reported, with a **0.8** review threshold.

The eval command writes machine-readable actual results to ignored
`data/evaluation.json`. Publish measured field numerators/denominators, acquisition
cost, latency, revision, and coverage here after a real run. A cache replay is
not a new paid run and must not be added to cumulative spend a second time.

## Remaining blockers

- API key must be supplied in a gitignored `.env` through the local filesystem.
- Live field accuracy/cost/latency and genuine response cache are pending.
- Cached demo timing is pending those responses.
- Full-sample completion may require a budget decision after the initial run;
  no spending above the authorized cap is permitted.
