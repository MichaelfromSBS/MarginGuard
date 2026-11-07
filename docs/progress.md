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

Review instructions: [checkpoint-1.md](checkpoint-1.md). No checkpoint 2 product functionality has been implemented.

## Demo dataset integration notes

The team's [demo corpus](../demo_data/README.md) was merged without rewriting it. It is an input package for upcoming development, not an already imported restaurant ledger. The built-in seed and canonical examples still use the checkpoint-1 catalog.

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

This reconciliation is pending; no adapter, document parser or historical bulk loader was added as part of the documentation update.

## Upcoming checkpoints

| Checkpoint | Required outcome | State |
| --- | --- | --- |
| 2 | Invoice and receipt ingestion, schema/business validation, mapping, persistence and deduplication | Not started |
| 3 | Actual sales metrics, recipe economics, completeness-aware forecasts and evaluation | Not started |
| 4 | Independent worker, automatic recomputation, measured alerts and notification delivery state | Not started |
| 5 | Read-only database tools, grounded owner chat and evidence-linked answers | Not started |

For each checkpoint, record the implementation commit, validation commands/results, contract changes, known limitations and team review decision. Do not move a planned feature to complete based only on a schema or fixture.
