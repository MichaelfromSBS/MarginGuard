# MarginGuard

**Restaurant finance monitoring from supplier invoices and customer sales receipts.**

NOVA 2026 · Carnegie Mellon University · DoorDash Back of House track

MarginGuard is being developed to maintain restaurant records automatically, connect ingredient-price changes to dish costs, project next month's sales and ingredient consumption, and explain significant changes through database-backed chat and evidence-linked alerts.

**Current status:** checkpoint 4 and the teammate's latest frontend are integrated. The independent worker processes documents, refreshes forecasts and creates two in-app notification types: one combined ingredient/overall projected-cost increase, and a next-day report about yesterday's unusual sales. Document issues remain Inbox review tasks. The bell and toasts use persistent acknowledgement state. Database-backed owner chat remains checkpoint 5. See [checkpoint 4](docs/checkpoint-4.md) for run instructions and the exact alert policy.

## Development progress

Last updated: **November 7, 2026**. API contract version: **1.0.0**.

| Milestone | Status | Delivered / acceptance boundary |
| --- | --- | --- |
| Reusable AI starter | Complete; prepared November 6 | React/TypeScript, FastAPI, OpenRouter transport, mock mode and streaming |
| Project specification | Current | [MarginGuard v2](docs/marginguard-plan-v2.md) defines the five product capabilities |
| Checkpoint 1: database and shared contract | Complete | SQLite schema, explicit demo seed, validated schemas, read APIs, OpenAPI, TypeScript and sample-data handoff |
| Team demo dataset v2 | Contract-validated; explicit bulk importer available | [History and demo documents](demo_data/README.md); eight invoices and 2,733 receipts |
| Checkpoint 2: document ingestion | Implemented; pending team review | PDF/image upload, structured extraction, validation, review/retry, duplicate-safe persistence and explicit fixture import |
| Checkpoint 3: metrics and forecasting | Implemented; pending team review | Sales/day/dish/channel summaries, effective recipe costs, completeness-aware next-month forecasts, sensitivity scenarios and held-out evaluation |
| Restaurant frontend integration | Merged and verified | Overview, Trends & Outlook, Inbox and explicit future-chat notice; forecast calculation/freshness and mobile navigation checked |
| Checkpoint 4: background processing and alerts | Implemented and integrated | Durable queue, automatic recalculation, combined cost alert, yesterday-only sales report and in-app acknowledgement |
| Checkpoint 5: database-backed chat | Planned | Read-only metric tools, grounded answers and evidence references |

See [the progress record](docs/progress.md) for commits, verification evidence and integration notes. Each checkpoint ends with a focused review before the next begins.

## Product workflow

The planned workflow is:

```text
Supplier invoices + customer sales receipts
                    ↓
       Extraction, validation and review
                    ↓
       Approved records in the database
                    ↓
    Sales metrics, recipe costs and forecasts
                    ↓
     Dashboard + owner chat + proactive alerts
```

AI interprets document language and explains retrieved results. Python owns financial calculations, unit conversions, forecast methods and measurable anomaly rules. Reported figures distinguish observed results, modeled costs and future projections.

## Technology

| Layer | Technology |
| --- | --- |
| Frontend | React, TypeScript, Vite |
| API | Python, FastAPI, Pydantic |
| Database | SQLite with transactional, checksummed migrations |
| Model access | OpenRouter through server-side asynchronous HTTP requests |
| Testing | pytest, mocked provider responses, Node's test runner |
| Planned processing | Independent Python worker and persisted jobs |

## Getting started

Prerequisites: Python **3.11+**, Node.js **22.12+** or a supported newer LTS, npm, and Git. The recorded checkpoint validation used Python 3.11.9 and Node.js 22.19.0 on Windows.

Clone the private repository using an account with access:

```bash
git clone https://github.com/MichaelfromSBS/nova-hackathon.git
cd nova-hackathon
python scripts/setup.py
```

Setup creates `.venv`, installs the dependency lockfiles and creates `.env` from `.env.example` only when `.env` does not already exist. Stop development servers before rerunning setup; Windows can lock the running bundler's native files.

Optionally load the small, explicitly fictional checkpoint-1 dataset:

```powershell
.\.venv\Scripts\python.exe -m backend.marginguard.seed
```

On macOS/Linux, use `.venv/bin/python -m backend.marginguard.seed`. Repeating the seed command is a no-op. It refuses to mix fixtures into an existing, unseeded business database. API startup applies migrations but never inserts demo financial records automatically.

For the full v2 history, use a separate fresh database instead of the small seed:

```powershell
.\.venv\Scripts\python.exe -m backend.marginguard.import_demo --database data/demo-v2.db
```

Set `MARGINGUARD_DATABASE_PATH=data/demo-v2.db` in `.env` before starting the server. This is explicit pre-approved fixture import, makes no model calls, and refuses to mix with the checkpoint-1 seed. See [checkpoint 2 setup and review](docs/checkpoint-2.md).

Start the API, independent worker and frontend:

```bash
npm run dev
```

- [MarginGuard dashboard](http://127.0.0.1:5173)
- [Interactive API documentation](http://127.0.0.1:8000/docs)
- [API capabilities](http://127.0.0.1:8000/api/capabilities)

Ctrl+C stops all three processes. Frontend edits reload automatically; restart after Python or `.env` changes. Ports 8000 and 5173 must be free. If PowerShell blocks `npm.ps1`, use `npm.cmd run dev`.

For backend-only development with reload:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

For queued document processing and automatic analytics, also run `.\.venv\Scripts\python.exe -m backend.worker` in another terminal using the same database settings. API-only uploads remain queued without the worker. `/api/worker` reports runtime health independently of API availability. See [checkpoint 4](docs/checkpoint-4.md).

## Configuration

Edit the local root `.env`:

```dotenv
AI_MODE=mock
OPENROUTER_API_KEY=
OPENROUTER_MODEL=
AI_TIMEOUT_SECONDS=60
AI_MAX_OUTPUT_TOKENS=1800
MARGINGUARD_DATABASE_PATH=data/marginguard.db
MARGINGUARD_UPLOAD_DIRECTORY=data/uploads
MARGINGUARD_EXTRACTION_MAX_OUTPUT_TOKENS=6000
```

Sales metrics and forecasting work without a model key. For live document extraction through Inbox, set `AI_MODE=openrouter`, add the team key, choose a current compatible model ID, and restart. Structured responses require compatible model/endpoint support; image input is a separate capability. See [OpenRouter's model catalog](https://openrouter.ai/models).

Checkpoint-2 HTTP extraction uses that same live configuration. In mock mode, uploads never fabricate approved financial records: extraction fails visibly with `live_model_required`. Offline history and single-document expected-output imports are separately labeled `fixture_history` and `fixture_expected` and are restricted to explicit demo use.

Live mode does not silently fall back to mock fixtures. Live OpenRouter extraction with Gemini 3.8 Flash has now been verified for the main demo PDF invoice and receipt in an isolated v2-history database. Both completed validation and ledger approval; this small smoke check does not establish general extraction accuracy. See the [progress record](docs/progress.md).

Environment variables override `.env`. Relative database paths resolve from the repository root. `.env`, local databases, uploads, caches and dependencies are excluded from Git. Keep keys server-side; do not put them in frontend code or `VITE_*` variables.

## Available API

| Method | Endpoint | Purpose |
| --- | --- | --- |
| GET | `/api/health` | Service, database and configuration status |
| GET | `/api/capabilities` | Checkpoint and feature availability |
| GET | `/api/restaurant` | Restaurant identity, currency, timezone and demo status |
| GET | `/api/catalog` | Ingredients, dishes, channels, menu prices and recipe versions |
| GET | `/api/ingredients/{ingredient_id}/prices` | Effective-dated ingredient prices and invoice-line references |
| GET | `/api/documents` | Paginated document metadata and processing status |
| GET | `/api/documents/{document_id}` | Document detail with available persisted source text |
| GET | `/api/documents/{document_id}/source` | Inspect a saved upload with hash-integrity checking |
| POST | `/api/documents` | Accept PDF/PNG/JPEG multipart upload and start bounded in-process extraction |
| POST | `/api/documents/{document_id}/review` | Validate a corrected extraction and record the review outcome |
| POST | `/api/documents/{document_id}/process` | Retry a failed/pending document from its saved bytes |
| GET | `/api/invoices` | Approved invoice records and line items |
| GET | `/api/receipts` | Approved receipt records and items |
| GET | `/api/coverage` | Complete, partial, unknown or closed date/channel coverage |
| POST | `/api/coverage/complete` | Audited confirmation of a finished day/channel or explicit closure |
| GET | `/api/sales` | Observed sales totals, breakdowns, coverage and sampled receipt evidence |
| GET | `/api/dishes/{dish_id}/cost` | Effective replacement recipe costs and channel contribution assumptions |
| GET | `/api/dashboard` | Actual/modeled metrics, dish costs and saved forecast for the as-of date |
| POST | `/api/forecasts/recalculate` | Calculate and persist a versioned next-calendar-month planning snapshot |
| GET | `/api/forecasts` | Paginated saved snapshots with freshness status |
| GET | `/api/forecasts/{run_id}` | Forecast details, daily/series values, ingredient requirements, scenarios and evaluation |
| GET | `/api/alerts` | Persistent evidence-based findings and in-app notification state |
| POST | `/api/alerts/{alert_id}/acknowledge` | Persist owner acknowledgement without changing financial facts |
| POST | `/api/alerts/{alert_id}/resolve` | Mark a reviewed finding resolved, preserving evidence |
| GET | `/api/worker` | Worker heartbeat, queue counts, new-alert count and safe processing errors |

Money and quantities are decimal strings. List endpoints return `items`, `total`, `limit` and `offset`. Product errors use a versioned `error` object. A fresh database returns empty catalogs/lists and a typed restaurant-not-configured response until configured or explicitly seeded.

Well-formed requests to the reserved business-chat route return **HTTP 501** until checkpoint 5. Calculations use Python and approved records, with no model request. Incomplete history produces explicit limitations and null restaurant forecast totals. The legacy workbench's `/api/run` and `/api/stream` remain separate from business-data chat.

Approved inputs immediately affect observed sales and effective recipe costs. They invalidate saved forecasts; the worker automatically refreshes current projections. The explicit recalculation endpoint remains available. Forecasts distinguish ingredient consumption from purchases/actual profit and sensitivity scenarios from statistical prediction intervals.

Uploads return HTTP 202 with a durable pending job; the independent worker advances document status. Poll for `completed`, `needs_review` or `failed`. Exact-byte duplicates return the existing ID, while different bytes with an existing invoice/receipt business key enter review. Images are labeled as visual evidence, without claiming an independent OCR quote check. See [checkpoint 2](docs/checkpoint-2.md) for formats/review and [checkpoint 4](docs/checkpoint-4.md) for queue/restart behavior.

Authoritative handoff artifacts:

- [Exported OpenAPI schema](docs/openapi.json)
- [Frontend TypeScript contracts](frontend/src/marginguard-api.ts)
- [Actual seeded read-response examples](examples/api)
- [Checkpoint 1 review checklist](docs/checkpoint-1.md)
- [Checkpoint 2 upload/review checklist](docs/checkpoint-2.md)
- [Checkpoint 3 calculation definitions and copyable test commands](docs/checkpoint-3.md)
- [Checkpoint 4 worker, anomaly policies and in-app notification review](docs/checkpoint-4.md)

## Demo data and document generation

There are two distinct fixture collections:

| Collection | Purpose | Current integration |
| --- | --- | --- |
| `examples/` and the built-in seed | Canonical contracts, paired source/expected extraction examples and a small ledger | Supported by the explicit seed command and contract tests |
| `demo_data/` | Contract-compatible JSONL history, paired invoice PDFs/text/JSON, image receipts and negative controls | Explicit validated bulk importer and shared approval tests |

Give the document-generating teammate [the sample-data contract and copyable Claude prompt](docs/sample-data-contract.md). Its examples specify stable IDs, decimal strings, timezone-aware timestamps and source references.

The v2 dataset replaces the earlier incompatible corpus. Its catalog IDs, decimal strings, timestamp offsets and status/coverage fields match the contract. The `seed` command still loads only the small checkpoint-1 ledger; `import_demo` loads the full v2 history into a fresh database. See [integration notes](docs/progress.md#demo-dataset-integration-notes).

PDF byte offsets must not be changed by Git line-ending conversion. `.gitattributes` marks PDF/image files appropriately; the original committed v2 PDFs are valid and were restored exactly on Windows. This fixes a checkout issue rather than regenerating business content.

All seeded financial records are fictional. The small checkpoint seed is not an eight-week forecasting history, and seeded records are not evidence that AI extraction has already processed their source documents.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest -q
npm run test:frontend
npm run build
```

On macOS/Linux, replace the first command with `.venv/bin/python -m pytest -q`. Tests isolate their databases from the configured local ledger.

Recorded checkpoint-2 verification: **180 backend tests passed**, **3 frontend parser tests passed**, production build and dependency consistency passed. Live HTTP checks verified upload, explicit mock failure, manual review approval, byte-identical deduplication and source retrieval. Subsequent Gemini compatibility verification passed **86 focused tests** plus real model extraction of the two main PDFs. Checkpoint-3 verification and numeric acceptance results are recorded in [the progress record](docs/progress.md). The test-client dependency emits one existing deprecation warning.

After an intentional contract change, regenerate the OpenAPI and seeded response artifacts:

```powershell
.\.venv\Scripts\python.exe scripts/export_contract.py
```

The exporter uses an isolated temporary database and leaves the configured business database untouched. Keep the TypeScript contracts aligned with intentional backend schema changes.

## Repository layout

```text
backend/
  main.py                    FastAPI application and starter endpoints
  config.py                  Environment-backed settings
  marginguard/
    db.py                    Connection and migration management
    migrations/              Versioned SQLite schema
    schemas.py               Versioned wire contracts
    routes.py                Read APIs, ingestion, review and future contracts
    document_io.py           Bounded PDF/PNG/JPEG reading
    extraction.py            Structured OpenRouter extraction
    validation.py            Arithmetic, catalog, units and evidence checks
    ingestion.py             Upload state, approval, review and retry
    analytics.py             Observed sales, coverage and replacement recipe costs
    forecasting.py           Versioned weekday-average projections and evaluation
    jobs.py                  Cross-process extraction claims and retry limits
    detectors.py             Measured findings, evidence and in-app alert state
    alert_explanations.py    Optional AI follow-up with deterministic fallback
    import_demo.py           Explicit validated full-history fixture importer
    fixture.py               Explicit offline single-document demonstration
    seed.py                  Opt-in fictional seed CLI
  worker.py                  Independent inbox/queue/analytics/alert process
frontend/src/
  App.tsx                    MarginGuard navigation and connection/alert state
  mg/                        Restaurant screens, API client and presentation helpers
  marginguard-api.ts          Product TypeScript contracts
docs/                        Plan, progress, review guide and OpenAPI export
examples/                    Canonical document pairs and API examples
demo_data/                   Team-contributed demo corpus
scripts/                     Setup, development launcher and contract exporter
tests/                       Database, API, contract and provider tests
data/                        Local runtime database; excluded from Git
```

## Scope and disclosure

The local application has no production authentication or deployment configuration. Model-supported interpretations and exact source matches do not establish that a business conclusion is correct. Cost projections describe ingredient consumption under stated assumptions, not actual net profit or a purchasing cash budget.

The reusable starter was prepared before the event. See [PREEXISTING.md](PREEXISTING.md) for the preparation inventory and disclose it accurately during judging. Preserve the distinction between fictional fixtures, recorded test results and functionality built during each checkpoint.
