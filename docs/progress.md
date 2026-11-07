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
| 2026-11-07 | Checkpoint 4 implemented | [`d858525`](https://github.com/MichaelfromSBS/nova-hackathon/commit/d858525): persistent worker, automatic forecasts and website-only notifications. Refined two-event policy is recorded below. |
| 2026-11-07 | Readability frontend merged | Teammate [`0bec869`](https://github.com/MichaelfromSBS/nova-hackathon/commit/0bec869), integrated in `75c22a1`, preserves simpler sales labels, compact Overview, supplier changes and dish-cost detail in Trends. |

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

## Checkpoint 4: persistent worker and website-only notifications

The initial checkpoint-4 implementation delivered the following foundation; the current two-event policy below supersedes its original four detector categories:

- `backend.worker` runs independently of browser/API requests. The development launcher starts API, worker and frontend together. `GET /api/worker` separates worker runtime health from API availability.
- Uploads enqueue durable extraction jobs by default. The inbox scanner watches separate invoice/receipt folders, waits for stable files, shares the upload hash/validation path and preserves originals. The old explicit inline mode remains available for compatibility tests.
- Migration 4 adds worker heartbeat/ownership, extraction job leases/backoff, file observations, saved version/date cursor and alert finding/revision/suggestion metadata. Migrations 1–3 remain immutable. Active claims fence review/retry/completion races; cancellation releases a claim, and expired interrupted jobs recover within the saved attempt budget.
- Approved record/coverage versions and local-date changes trigger automatic current-forecast refresh. Cached policy/date/source versions prevent duplicate snapshots. No owner question or Calculate button is required.
- Deterministic price-spike, fixed-demand projected-cost, recent-complete-day sales and data-quality checks persist measured facts and source references. Repacked/same-price and late older invoices do not create duplicate price/cost events. Data corrections update/resolve supported findings without modifying their source financial facts.
- Stable alert IDs/revisions and new/acknowledged/resolved state power the existing website bell/toasts. Acknowledgement survives restarts. No external delivery implementation/configuration is included; the unused legacy notification-outbox table remains empty.
- Optional AI follow-up is supplementary to the committed measured message. Provider/format/number-validation failures retain the deterministic suggestion, so an AI failure cannot erase the alert or change its numeric evidence.
- Existing `.env` key/model/database values were preserved, and missing worker/inbox/AI-suggestion settings were added. Frontend wording/component files were not edited; only the shared TypeScript API contract changed.

Recorded final verification:

| Check | Result |
| --- | --- |
| Full backend suite | **220 passed**, one existing test-client deprecation warning |
| Frontend tests / TypeScript / build | **7 passed**; production build and type checking passed |
| Focused final worker suite | **17 passed**: queue, scanner stability, retries, lease fencing, cancellation/restart, evidence, correction and persistent in-app state |
| Independent API + worker, actual model extraction | Watched main invoice completed with Gemini/OpenRouter; automatic December cost became $10,143.80, revenue $31,286.93; three measured alerts; duplicate ledger/alert prevention after an expired-lease restart; original bytes and SQLite integrity passed |
| Final website-only browser check | Toast appeared without a prompt; bell count 1 → 3 → 2 after acknowledgement; automatic forecast showed $10,143.80; no JavaScript errors. Used isolated mock mode plus explicit validated fixture insertion to test the website/worker path without another paid call |
| External notification boundary | No external owner messages sent; legacy external outbox remained empty in the final browser/database check |
| Schema upgrade | Versions 1–3 upgrade to 4 preserving an existing row; checksummed migration behavior remains tested |
| Contract handoff | OpenAPI, capabilities/worker/read examples and TypeScript contract updated; [checkpoint 4 guide](checkpoint-4.md) includes startup and review commands |

Policy clarification: the agreed unusual-sales rule uses **units**: November 5 has 39 units against an 80.5-unit prior-weekday mean, down 51.55279503%. The fixture answer key's roughly 51.3% figure uses revenue. The default alert window covers seven finished dates and uses eight weeks for prior comparisons. October 14 unknown coverage and November 7 partial/current coverage are excluded; October 25 is outside the recent alert window.

The worker remains a local single-database service, with explicit leases and bounded serial provider work. Chat tools and grounded owner answers remain checkpoint 5. Existing user databases were not reset; test processes/databases were isolated.

## Current alert policy and latest frontend integration

The updated frontend is integrated with the worker. Overview retains the teammate's simpler labels and layout, links to Trends/Inbox and shows current supplier changes. Integration fixes preserve accurate seven-day coverage wording, select same-day ingredient prices from the backend's chosen invoice evidence, avoid division by a zero menu price, and show a monitoring-unavailable warning instead of a false all-clear state. Combined alert text uses the full mobile width above its acknowledgement button.

The system now generates only:

1. **One combined ingredient/overall cost increase notification per source invoice.** At least one consumed ingredient must get more expensive and the net fixed-demand monthly ingredient consumption cost must increase after cent rounding. The message names the ingredient causes and before/after total cost. There are no separate ingredient-price popups and no former 10%/$50 gates. Offsetting decreases, zero demand and insufficient forecast inputs suppress a positive total-cost notification. Contributions reconcile to the displayed total. Duplicate scans, repacks, late older invoices and month rollover do not re-announce a known supplier change.
2. **A report about yesterday's unusual sales, issued the next restaurant-local day.** Only yesterday's fully complete channels qualify against the existing four-weekday, >30% and >=10-unit drop policy. The report includes orders, units, net revenue, comparison dates and absolute report/sale dates. It can wait for coverage completion later the next day, but does not catch up older days or alert intraday.

Document failures remain Inbox review tasks without new business alerts/toasts/bell counts. Migration 5 resolves earlier notification-policy events before the API serves them, preserving their evidence and facts as archived history. Existing v2 reports retain acknowledgement state. API alert lists return newest first so old archives cannot displace current findings.

Validation: **230 backend tests passed**, **7 frontend tests passed**, production build/type checking passed. New acceptance cases cover the next-day boundary, incomplete-yesterday completion, no historical catch-up, a small 0.25% ingredient increase with a $10.14 total effect, net offsets/zero demand/missing inputs, cost attribution, month-rollover deduplication and migration from schema 4 with preserved legacy evidence. Follow-up API/migration checks exercise current-first alert pagination.

An isolated browser check verified the latest Overview/Trends navigation, one combined cost toast and one bell item, automatic $10,143.80 forecast cost, $3.96 Classic Burger cost, acknowledgement clearing the bell, and an unavailable-monitoring warning when the worker lease becomes stale. Desktop/mobile layouts were inspected; no JavaScript errors or page overflow occurred. The fixture insertion was explicit and fictional; no extra model calls or external owner notifications were used. User `.env` values, runtime data and `.vscode/` were preserved.

The November 5 fixture anomaly is reported on November 6 only; a new November 7 run produces no historical sales alert. The main beef invoice produces one combined notification linking $4.00 → $4.72/lb to the $730.17 monthly projected ingredient-cost increase. See [checkpoint 4](checkpoint-4.md) for the current review sequence.

## Checkpoint 5: database-grounded owner chat

Implemented November 7, 2026; pending team review. The existing `.env`, business databases and teammate files were preserved. Implementation committed as [`e8dab40`](https://github.com/MichaelfromSBS/nova-hackathon/commit/e8dab40); the subsequent teammate frontend integration is recorded below.

- `POST /api/chat` now makes one structured OpenRouter planning request, validates at most four allowlisted calls, and returns Python-rendered answers with exact decimal metrics, periods, coverage, source versions, evidence and executed query traces. The model does not generate financial figures or SQL.
- Six tools cover approved sales and rankings, normalized ingredient-price history, recipe replacement costs, existing monthly forecasts, existing alerts and compatible saved-forecast attribution. Forecast comparison separates usage/dish mix, supplier-price, interaction and rounding effects and names the main changed ingredients.
- All tools share one query-only SQLite snapshot with a query budget. History is bounded to six messages of 2,000 characters; independent questions clear earlier filters while explicit follow-ups can refer back. Known period/channel/entity mismatches produce clarification. Unknown tools, extra arguments, mutations, unsupported business claims and malformed/incomplete model output do not produce invented answers.
- Stale/missing forecasts are unavailable without triggering calculation. Historical comparisons retain immutable originally-ready values and report historical versions honestly. No schema migration, ledger write, chat acknowledgement or external owner notification was added.
- Ask MarginGuard displays real metric cards, readable answers, expandable source excerpts, document links into Inbox, and query traces. Chat remains in memory across tab/source navigation. Provider/configuration/credit/timeout errors remain visible. Mock chat explicitly requires a real configured model rather than pretending to understand questions.
- Health/capabilities report checkpoint 5; TypeScript/OpenAPI contracts and a transparent canned-planner chat example are exported. [Checkpoint 5](checkpoint-5.md) provides copyable PowerShell checks, configuration and support boundaries.

Verification on an isolated fictional full-history database:

| Check | Result |
| --- | --- |
| Backend regression suite | **349 tests passed**; one existing Starlette/httpx deprecation warning |
| Focused chat/API, read tools and saved-comparison tests | 74 + 26 + 19 cases, including provider errors, incomplete plans, read-only transaction enforcement, date/filter mismatches, stale forecasts, evidence and attribution |
| Frontend checks | **7 tests passed**, TypeScript/production build passed |
| Dependencies and contract | `pip check`, contract exporter and diff whitespace checks passed |
| Actual configured OpenRouter model | Returned $7,400.00/332 orders/610 units, Classic Burger $3.96, beef $4.00 → $4.72/lb, calendar-week delivery totals and the $730.17 saved-forecast price effect |
| Live browser | Desktop and 390px mobile, delivery follow-up, invoice/receipt source navigation, retained chat and named beef-cost attribution passed; no page errors or horizontal overflow |
| Read-only boundary | Ledger dumps unchanged before/after live API questions; automated tests also prove SQLite rejects an attempted write inside a tool |

The first complex Gemini plan was truncated under the original 1,800-token output budget. The final defaults use 3,000 tokens and automatic low reasoning for Gemini; other model families preserve provider defaults. The same forecast-change question then passed live API and browser checks. Reasoning/provider bodies are never exposed in owner answers. No real model correctness guarantee is implied by these smoke checks; routing remains bounded and visible for review.

The browser test used a temporary imported history, explicitly approved fictional invoice fixture and saved before/after projections. The local test server was stopped afterward. Existing user runtime data, `.env` values and `.vscode/` were not changed. The full-history forecast and alerts are not fabricated when inputs are missing.

## Teammate alert lifecycle and Overview chat integration

Integrated teammate commits [`ed82757`](https://github.com/MichaelfromSBS/nova-hackathon/commit/ed82757) and [`c5035f2`](https://github.com/MichaelfromSBS/nova-hackathon/commit/c5035f2) with checkpoint 5 (`e8dab40`).

- Acknowledge moves a new alert into a separate expandable Acknowledged list and refreshes the bell immediately. Resolve persists the handled status and removes the finding from both live lists. Both lists query their own status, so resolved archives do not displace their first page. The existing two detector types and website-only notification policy are unchanged.
- Chat sits at the bottom of Overview; the separate Ask tab is removed. Responses scroll inside the bounded panel, without jumping to chat on initial load. Checkpoint-5 metrics, history, errors, query traces and source links remain connected. Overview stays mounted across navigation so visiting a source in Inbox does not discard the conversation.
- Retained the teammate's clearer ingredient-usage table, per-unit prices, consumption-versus-purchase explanation and summed forecast ingredient cost.

Verification: **128 focused backend tests passed** (worker/alerts, API and chat), **7 frontend tests passed**, TypeScript and production build passed. The complete checkpoint-5 suite had passed **349 tests** before this frontend-only merge. An isolated live browser check verified acknowledge → separate list → resolve, immediate bell clearing, acknowledgement after reload, persisted resolved status, Overview chat placement, initial page scroll at zero, real beef-price and Classic Burger answers, internal chat scrolling, PDF source HTTP 200, retained history through Inbox, and the forecast ingredient table. Desktop and 390px mobile screenshots were inspected; no page errors or horizontal overflow occurred.

The test used a copied fictional database and an explicit local detector cycle, with optional AI alert suggestions disabled. Only chat used the configured model. Existing `.env`, business data and `.vscode/` were preserved; the temporary review server was stopped afterward.

## Live receipt visibility fix

Verified the teammate's report and reproduced it with a regression test: a PDF receipt was approved immediately, but default sales/dashboard requests ended yesterday and hid its current-day sales. Receipt persistence and data-version invalidation were already working. Supplier replacement costs already included the current as-of date.

The receipt visibility fix includes:

- Default `/api/sales` and `/api/dashboard` periods now include the restaurant-local as-of date plus six previous dates. Overview and daily-sales charts poll every three seconds and explain that today's receipts are still in progress. Explicit historical start/end queries retain their requested ranges.
- Chat's default/last-seven-day sales use the same live period. A `today` tool period reports approved receipts so far; `last_7_finished_days` preserves an explicitly requested yesterday-ending range. Last calendar week and last seven complete days keep their distinct meanings.
- Receipt approval still increments the data version and refreshes the saved forecast. Partial current-day receipts are not treated as full-day demand samples. Tomorrow's unusual-sales notification policy is unchanged. Queued, failed or review-held receipts do not change financial figures; byte duplicates cannot count twice.

Validation: **353 backend tests passed**, **7 frontend tests passed**, TypeScript/production build, contract export and whitespace checks passed. New cases cover browser-style multipart upload → worker extraction/approval → default live metrics and daily breakdown, exact order/unit/net-sales deltas, live chat tools, forecast freshness without partial-day training leakage, duplicate idempotency, review-held exclusion and restaurant midnight versus UTC midnight.

A live configured-model check approved the actual fictional `1_receipt_TB-20261107-001.pdf`. On November 7 the live November 1–7 totals increased from **$5,932.00 / 264 orders / 488 units** to **$5,969.00 / 265 orders / 491 units**. Today appeared in the daily chart; owner chat reported **$37.00 / 1 order / 3 units**, with partial coverage and source references. The forecast refreshed to the new source version while retaining its finished-day demand totals. Desktop/mobile browser checks passed without page errors or horizontal overflow.

The browser used a separate localhost port and an isolated copied fixture database; test-only request forwarding preserved the production local-origin guard. Existing user server, `.env` and business data were preserved. Temporary API/worker processes were stopped. Restart the existing API and worker (or restart `npm.cmd run dev`) to load the fix: the running API on port 8000 still uses the older period behavior until restarted.

## Checkpoint review status

| Checkpoint | Required outcome | State |
| --- | --- | --- |
| 2 | Invoice and receipt ingestion, schema/business validation, mapping, persistence and deduplication | Implemented; pending review |
| 3 | Actual sales metrics, recipe economics, completeness-aware forecasts and evaluation | Implemented; frontend integrated and verified |
| 4 | Independent worker, automatic recomputation, two focused in-app notification types | Implemented; latest frontend integrated and verified |
| 5 | Read-only database tools, grounded owner chat and evidence-linked answers | Implemented; frontend integrated and verified; pending team review |

For each checkpoint, record the implementation commit, validation commands/results, contract changes, known limitations and team review decision. Do not move a planned feature to complete based only on a schema or fixture.
