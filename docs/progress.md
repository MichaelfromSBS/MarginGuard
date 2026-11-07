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
| 2026-11-07 | Checkpoint 2 implemented | [`84a4f97`](https://github.com/MichaelfromSBS/nova-hackathon/commit/84a4f97): ingestion, extraction, validation, review/retry, source integrity and explicit fixture/history import. |
| 2026-11-07 | Dataset folder flattened | Teammate commit [`3840d46`](https://github.com/MichaelfromSBS/nova-hackathon/commit/3840d46) moves the v2 corpus directly under `demo_data/`. Importer, tests and documentation paths were updated after merging it. |
| 2026-11-07 | Gemini compatibility fix published | [`376042a`](https://github.com/MichaelfromSBS/nova-hackathon/commit/376042a): provider schema compatibility, preserved local item bounds and live extraction verification. |
| 2026-11-07 | Checkpoint 3 implemented | [`8767d3c`](https://github.com/MichaelfromSBS/nova-hackathon/commit/8767d3c): observed sales, evidence-linked replacement recipe costs, audited coverage confirmation and versioned weekday-average forecasts. |
| 2026-11-07 | Restaurant frontend integrated | Teammate frontend [`e89557b`](https://github.com/MichaelfromSBS/nova-hackathon/commit/e89557b) merged with checkpoint 3 in `0a5ee2b`, followed by integration fixes and verification below. |

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

The team replaced the original corpus with [contract-compatible v2 data](../demo_data/README.md) in commit `0ed21bd`. The differences below describe the original corpus and are resolved by v2. The small built-in seed and full historical importer remain deliberately separate.

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
- Structured OpenRouter extraction uses separate invoice/receipt schemas, known catalogs and a bounded output budget. Provider success/failure paths are tested with mocked responses; subsequent live verification is recorded below.
- Decimal arithmetic, source-page quotes, catalog matching, quantities, pack units and document totals are checked before a whole-document ledger transaction.
- Ambiguous input and business-key conflicts enter review without changing financial rows. Exact-byte duplicates reuse the document and do not call a model again.
- Corrections are audited, retries preserve source integrity, approved records cannot be overwritten through review, and new receipt data marks its day/channel partial.
- Schema migration 2 adds extraction/review provenance, durable data changes, pending jobs, vendors and the business calendar while preserving schema-1 records.
- Explicit `fixture_history` and `fixture_expected` paths support offline review without pretending expected JSON is an AI result.
- The PDF parser issue was traced to Git Windows LF-to-CRLF checkout conversion. Committed PDFs are valid. Binary attributes now protect their offsets and local copies were restored byte-for-byte; business content was unchanged.

Review guide: [checkpoint-2.md](checkpoint-2.md). At the checkpoint-2 boundary, forecasting, folder watching, anomaly alerts, webhook sending and database-backed business chat remained unimplemented. Checkpoint 3 below adds metrics and forecasting. Request-process tasks are not the independent checkpoint-4 worker; pending jobs need explicit retry after interruption.

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
| Real OpenRouter extraction | Initially not run; subsequent live verification is recorded below |

The baseline v2 history was loaded separately into local `data/demo-v2.db`. Existing `.env` database selection and credentials were preserved; select that database explicitly to serve the full history. Runtime databases and uploaded originals remain outside Git.

## Checkpoint 2: Gemini compatibility fix and live verification

November 7: the team's first live uploads failed with `provider_request_rejected`. A basic request with the configured model succeeded. Reproducing the extraction payload returned HTTP 400 with Gemini's `INVALID_ARGUMENT`; removing only the item array's `maxItems: 200` constraint made the request succeed. The provider request now omits that one constraint. The original Pydantic model still rejects more than 200 items before ledger persistence; required fields, types, Decimal checks and source-evidence validation remain enforced.

- Focused extraction, ingestion and business-validation suites: **86 passed**, with the existing test-client deprecation warning. Regression cases cover both invoice and receipt item limits after provider generation.
- Live OpenRouter calls using the configured Gemini 3.8 Flash model processed both main demo PDFs in an isolated temporary database loaded with the full v2 history. Both finished `completed`, with `extraction_method: openrouter` and no validation issues.
- Approved counts changed from 8 to 9 invoices and 2,733 to 2,734 receipts. The new November 7 beef price was **$4.72/lb**. Reuploading both originals returned the same document IDs and added no records.
- The user's running server/database and `.env` were preserved. Existing failed documents need a server restart followed by `POST /api/documents/{id}/process`; identical-byte reupload alone does not retry.

This verifies these two PDF examples, not general extraction accuracy or live image extraction. `/api/health` checks configuration presence rather than making a paid provider probe.

## Checkpoint 3: completed implementation, pending team review

Delivered on November 7:

- `analytics.py`: observed completed-receipt units/orders/net item revenue, inclusive date/dish/channel filtering, per-day/dish/channel breakdowns, bounded receipt evidence and explicit completeness. Tax/tips are excluded and allocated item discounts are already reflected in net amounts.
- Effective-date recipe cost lookup with lb/oz conversion, latest compatible approved prices, invoice-line evidence and channel contribution assumptions. Missing/invalid recipe inputs return limitations and null modeled costs rather than zero.
- `forecasting.py`: next-calendar-month weekday averages, configurable 4–26-week history (default eight), at least four complete observations per applicable weekday, explicit calendar/channel closures and zero-versus-missing handling. No model calls or new dependencies.
- Daily and dish/channel demand projections, ingredient requirements/costs, reconciled money totals, ±15% default sensitivity scenarios and seven-day held-out evaluation against a seasonal-naive baseline. Synthetic-data MAE is not evidence of real-world monthly accuracy.
- Migration 3 adds immutable forecast calculation snapshots, policy/version cache keys and audited coverage events. Earlier migrations are unchanged. Approved inputs and coverage changes mark saved runs pending; explicit recalculation produces a current-version snapshot. Repeating the same date/policy/version returns the same run.
- Live dashboard/sales/dish-cost/forecast APIs, explicit coverage confirmation, checkpoint-3 health/capabilities, exported OpenAPI, updated TypeScript interfaces and sales/dish-cost/dashboard examples. Subsequent frontend integration is recorded below.
- [Checkpoint 3 review guide](checkpoint-3.md) with exact PowerShell commands, expected figures, API definitions and planning limitations. Existing runtime files, `.env`, user server and `.vscode/` were preserved.

Recorded verification:

| Check | Result |
| --- | --- |
| Full backend suite | **202 passed**, one existing test-client deprecation warning |
| Frontend streaming parser | **3 passed** |
| Type checking and production build | Passed |
| Separate real HTTP server, isolated full-history database | Health checkpoint 3, observed sales, ready forecast, persisted detail/list/dashboard, repeat-calculation cache and reserved chat boundary passed |
| Numeric fixture acceptance | Oct 31–Nov 6: 332 orders, $7,400.00 net item revenue; December: $31,286.93 revenue, $9,413.63 ingredient consumption cost before the beef invoice |
| Repricing acceptance | Classic $3.60 → $3.96; December ingredient consumption cost $9,413.63 → $10,143.80, a $730.17 increase at unchanged demand/revenue |
| Coverage and leakage checks | Unknown/partial days excluded, explicit complete zero included, unfinished-day confirmation rejected, per-weekday sample guard enforced, final-seven-day holdout excluded from fitting |
| Ledger/version boundaries | Partial-day receipt updates actuals, invalidates old run, and does not enter training; repeated calculation/import adds no duplicate forecast/ledger record |
| Migration/integrity | Schema 1 and 2 upgrade to 3 preserving an existing row; isolated HTTP database foreign-key and integrity checks passed |
| Missing inputs and aggregation | Missing prices/incompatible units block modeled costs; incomplete series do not publish partial restaurant totals; daily/series/ingredient totals reconcile |

Checkpoint 3 is deterministic analytics, not an additional AI feature. The existing extractor supplies the approved records it uses. Automatic forecast recomputation, anomaly findings/notifications and business-data chat remain checkpoints 4–5. No actual business database was reset and no paid provider requests were needed for this checkpoint.

## Restaurant frontend review and integration

The teammate's Overview, Trends & Outlook, Ask and Inbox screens were reviewed and merged with checkpoint 3. The merge preserved both histories and the checkpoint-3 API contracts.

Integration fixes:

- Added Calculate/Recalculate forecast controls using the actual calculation endpoint. Overview and Trends use the current as-of dashboard snapshot rather than an arbitrary older saved run. Pending/insufficient snapshots cannot display old numeric totals as a ready current forecast.
- Connected daily sales, consumption requirements, demand sensitivity scenarios, evaluation and modeled menu ingredient costs. Replaced hardcoded December titles with the actual horizon and labeled monitoring unavailable until checkpoint 4.
- Corrected receipt net revenue to subtract allocated discounts using decimal-string/BigInt arithmetic. Preserved fixture/manual/AI provenance labels.
- Remount document detail when selection changes, prevent overlapping poll requests, clear data when changing queries, and show retry failures rather than swallowing them.
- Fixed the narrow-screen navigation row and table scrolling while preserving the teammate's visual design.

Verification: **202 backend tests**, **7 frontend tests**, TypeScript and production build passed. Frontend regression tests cover discounted revenue/rounding, stale-total suppression and forecast readiness. An isolated real-browser check verified observed $7,400 sales, UI forecast calculation, invoice upload in mock mode followed by explicit manual review, stale suppression, recalculation to $10,143.80 ingredient cost, original PDF retrieval, the honest checkpoint-5 chat notice and navigation at 390px width. No JavaScript errors or page-level horizontal overflow were observed. Desktop/mobile screenshots were inspected. Browser review used a temporary database and no paid extraction; the user's database and `.env` were preserved.

## Upcoming checkpoints

| Checkpoint | Required outcome | State |
| --- | --- | --- |
| 2 | Invoice and receipt ingestion, schema/business validation, mapping, persistence and deduplication | Implemented; pending review |
| 3 | Actual sales metrics, recipe economics, completeness-aware forecasts and evaluation | Implemented; frontend integrated and verified |
| 4 | Independent worker, automatic recomputation, measured alerts and notification delivery state | Not started |
| 5 | Read-only database tools, grounded owner chat and evidence-linked answers | Not started |

For each checkpoint, record the implementation commit, validation commands/results, contract changes, known limitations and team review decision. Do not move a planned feature to complete based only on a schema or fixture.
