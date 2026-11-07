# MarginGuard progress record

Last updated: November 7, 2026. This record distinguishes implemented functionality, verification and pending work. It does not imply that the team has approved a checkpoint merely because implementation is committed.

## Milestone history

| Date | Milestone | Record |
| --- | --- | --- |
| 2026-11-06 | Generic starter prepared | React/TypeScript workbench, FastAPI, OpenRouter transport, mock mode, streaming and setup/test scripts. See [pre-existing inventory](../PREEXISTING.md). |
| 2026-11-07 | Repository initialized | [`a9e9c28`](https://github.com/MichaelfromSBS/nova-hackathon/commit/a9e9c28): starter and planning documents. |
| 2026-11-07 | Product scope revised | [MarginGuard v2](marginguard-plan-v2.md): invoices, receipts, forecasts, grounded chat and automatic alerts. |
| 2026-11-07 | Checkpoint 1 implemented | [`8e74884`](https://github.com/MichaelfromSBS/nova-hackathon/commit/8e74884): SQLite foundation, schemas, explicit seed, read APIs, OpenAPI, TypeScript and sample-data handoff. |
| 2026-11-07 | Team demo corpus contributed | [`291062e`](https://github.com/MichaelfromSBS/nova-hackathon/commit/291062e): restaurant configuration, history, PDF/image documents and expected outputs. Integration remains pending. |
| 2026-11-07 | Parallel work merged | [`f47d90b`](https://github.com/MichaelfromSBS/nova-hackathon/commit/f47d90b): preserved checkpoint 1 and the contributed dataset. Resolved the `.gitignore` overlap by retaining both sets of runtime-data exclusions. |

## Checkpoint 1: completed implementation, pending team review

Delivered:

- Transactional, checksummed SQLite migrations and short-lived connections with foreign-key enforcement.
- Canonical decimal-string and supported-unit constraints; persistent document/business duplicate protection.
- Explicit idempotent seed CLI, with refusal to mix fixtures into an existing unseeded business database.
- Fictional seed containing one restaurant, five ingredients, three dishes, two channels, two invoices, three receipts, effective price history and coverage records.
- Read endpoints for the restaurant, catalog, document metadata/detail, invoices, receipts, coverage, ingredient prices and persisted alerts.
- Versioned product error responses and feature-capability metadata.
- Future endpoint contracts returning explicit 501 responses rather than simulated live results.
- OpenAPI export, TypeScript types, canonical source/expected extraction pairs, actual API examples and a copyable document-generation prompt.
- Local `.env` ready for team configuration; existing values preserved and excluded from Git.

Recorded verification on November 7:

| Check | Result |
| --- | --- |
| Full backend suite | 86 passed; one test-client deprecation warning |
| Frontend streaming-parser tests | 3 passed |
| Type checking / production build | Passed |
| Python dependency consistency | Passed |
| Explicit seed repeated twice | First invocation inserted fixtures; second was a no-op |
| SQLite integrity | Foreign-key check passed |
| Live API smoke check | Health, capabilities, catalog, invoices, receipts, source detail and API docs returned 200 |
| Future-feature behavior | Dashboard returned typed HTTP 501 |
| Publication exclusions | `.env`, runtime database and uploads excluded |

These results cover the checkpoint implementation and canonical examples. They do not establish model extraction accuracy, forecast quality or correctness of every record in the contributed dataset.

Review instructions: [checkpoint-1.md](checkpoint-1.md). The following checkpoint-2 section records the newer implementation.

## Demo dataset integration notes

The team replaced the original corpus with [contract-compatible v2 data](../demo_data/demo_data_v2/README.md) in commit `0ed21bd`. The differences below describe the original corpus and are resolved by v2. The small built-in seed and full historical importer remain deliberately separate.

Resolve these differences explicitly during checkpoint 2 and update shared contracts together if needed:

| Area | Contributed dataset | Current contract / required decision |
| --- | --- | --- |
| Menu and recipes | Classic Burger, chicken sandwich, side fries and additional individual ingredients | Built-in seed uses Classic Burger, Cheeseburger, Veggie Burger and a smaller catalog. Choose/load the intended catalog; do not silently alias different dishes. |
| Units | Includes `slice` | Wire contract supports `lb`, `oz`, `each`, plus purchase `case`. Model a cheese slice as one canonical countable item or extend supported units deliberately. |
| Monetary representation | Expected extraction JSON includes numeric values | Canonical model outputs use decimal strings; bulk CSV ingestion should parse original strings with Decimal rather than introduce binary-float rounding. |
| Field names | Examples include `receipt_id`, `datetime`, `channel`, `qty`, `line_amount`, `supplier`, `invoice_no` | Map to canonical extraction fields or agree a versioned contract change. Paired canonical examples live in `examples/`. |
| Timestamps | Historical CSV uses local timestamps without offsets | Interpret in America/New_York with date-appropriate offsets; canonical API timestamps are timezone-aware. Handle the daylight-saving transition explicitly. |
| Receipt status | Corpus describes `voided` and `refunded` | Contract uses `void` and `refund`. Map semantics and establish treatment of returns before calculating totals. |
| Coverage | Date-level rows, including `missing` | Current coverage is date-and-channel based with `complete`, `partial`, `unknown`, `closed`. Confirm scope before expanding date rows across channels; missing data is not zero sales. |
| Financial expectations | Dataset-specific recipes, discounts, forecast values and answer key | Recalculate from approved mapped records. Do not force original illustrative burger amounts or forecasts onto different recipes. |

Checkpoint 2 validates the v2 schemas, literal source quotes and normalized catalog IDs. The explicit bulk importer approves all eight historical invoices and 2,733 receipts atomically through the same business validator used for uploads. It records fixture provenance, makes no model calls and refuses a nonempty mixed ledger. The original corpus's answer key is not used for v2 calculations.

## Checkpoint 2: completed implementation, pending team review

- Upload endpoints persist supported PDF/PNG/JPEG bytes under generated names and start bounded in-process extraction tasks.
- Structured OpenRouter extraction uses separate invoice/receipt schemas, known catalogs and a bounded output budget. No key/model is configured locally, so actual paid extraction remains unverified; provider success/failure paths are tested with mocked responses.
- Decimal arithmetic, source-page quotes, catalog matching, quantities, pack units and document totals are checked before a whole-document ledger transaction.
- Ambiguous input and business-key conflicts enter review without changing financial rows. Exact-byte duplicates reuse the document and do not call a model again.
- Corrections are audited, retries preserve source integrity, approved records cannot be overwritten through review, and new receipt data marks its day/channel partial.
- Schema migration 2 adds extraction/review provenance, durable data changes, pending jobs, vendors and the business calendar while preserving schema-1 records.
- Explicit `fixture_history` and `fixture_expected` paths support offline review without pretending expected JSON is an AI result.
- The PDF parser issue was traced to Git Windows LF-to-CRLF checkout conversion. Committed PDFs are valid. Binary attributes now protect their offsets and local copies were restored byte-for-byte; business content was unchanged.

Review guide: [checkpoint-2.md](checkpoint-2.md). Forecasting, folder watching, anomaly alerts, webhook sending and database-backed business chat remain unimplemented. Request-process tasks are not the independent checkpoint-4 worker; pending jobs need explicit retry after interruption.

Recorded checkpoint-2 verification on November 7:

| Check | Result |
| --- | --- |
| Full backend suite | 180 passed; one existing test-client deprecation warning |
| Frontend build and parser tests | Build passed; 3 parser tests passed |
| Dependency consistency | Passed |
| Full v2 history import | 8 invoices, 2,733 receipts, 2,741 approved documents; repeated import is a no-op |
| Import rejection/rollback | Mixed database refused; invalid late fixture rolls back whole import |
| Ingestion edge cases | Exact duplicates, conflicting keys, ambiguity, correction, retry, source tampering, image evidence and late invoices tested |
| Schema upgrade | Existing schema-1 business row preserved through migration 2 |
| Live HTTP on an isolated demo copy | Upload 202, honest mock failure, explicit manual correction, duplicate same ID, one receipt added, original source bytes returned |
| Real OpenRouter extraction | Not run: no API key/model configured |

The baseline v2 history was loaded separately into local `data/demo-v2.db`. Existing `.env` database selection and credentials were preserved; select that database explicitly to serve the full history. Runtime databases and uploaded originals remain outside Git.

## Upcoming checkpoints

| Checkpoint | Required outcome | State |
| --- | --- | --- |
| 2 | Invoice and receipt ingestion, schema/business validation, mapping, persistence and deduplication | Implemented; pending review |
| 3 | Actual sales metrics, recipe economics, completeness-aware forecasts and evaluation | Not started |
| 4 | Independent worker, automatic recomputation, measured alerts and notification delivery state | Not started |
| 5 | Read-only database tools, grounded owner chat and evidence-linked answers | Not started |

For each checkpoint, record the implementation commit, validation commands/results, contract changes, known limitations and team review decision. Do not move a planned feature to complete based only on a schema or fixture.
