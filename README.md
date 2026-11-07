# MarginGuard

**Restaurant finance monitoring from supplier invoices and customer sales receipts.**

NOVA 2026 · Carnegie Mellon University · DoorDash Back of House track

MarginGuard is being developed to maintain restaurant records automatically, connect ingredient-price changes to dish costs, project next month's sales and ingredient consumption, and explain significant changes through database-backed chat and evidence-linked alerts.

**Current status:** checkpoint 2 is implemented and awaiting team review. Uploads, extraction, deterministic validation, correction/retry and duplicate-safe ledger persistence work. Forecasting, the independent worker, alerts and business-data chat remain subsequent checkpoints. The frontend currently shows the original generic AI workbench; use the API docs for ingestion review.

## Development progress

Last updated: **November 7, 2026**. API contract version: **1.0.0**.

| Milestone | Status | Delivered / acceptance boundary |
| --- | --- | --- |
| Reusable AI starter | Complete; prepared November 6 | React/TypeScript, FastAPI, OpenRouter transport, mock mode and streaming |
| Project specification | Current | [MarginGuard v2](docs/marginguard-plan-v2.md) defines the five product capabilities |
| Checkpoint 1: database and shared contract | Complete | SQLite schema, explicit demo seed, validated schemas, read APIs, OpenAPI, TypeScript and sample-data handoff |
| Team demo dataset v2 | Contract-validated; explicit bulk importer available | [History and demo documents](demo_data/README.md); eight invoices and 2,733 receipts |
| Checkpoint 2: document ingestion | Implemented; pending team review | PDF/image upload, structured extraction, validation, review/retry, duplicate-safe persistence and explicit fixture import |
| Checkpoint 3: metrics and forecasting | Planned | Sales summaries, recipe costs, completeness-aware next-month projections |
| Checkpoint 4: background processing and alerts | Planned | Persistent worker, automatic recalculation, measured anomalies and notification state |
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

Start both services:

```bash
npm run dev
```

- [Starter frontend](http://127.0.0.1:5173)
- [Interactive API documentation](http://127.0.0.1:8000/docs)
- [API capabilities](http://127.0.0.1:8000/api/capabilities)

Ctrl+C stops both services. Frontend edits reload automatically; restart after Python or `.env` changes. Ports 8000 and 5173 must be free. If PowerShell blocks `npm.ps1`, use `npm.cmd run dev`.

For backend-only development with reload:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

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

Checkpoint 1 works without a model key. For a live call through the existing generic workbench, set `AI_MODE=openrouter`, add the team key, choose a current compatible model ID, and restart. Structured responses require compatible model/endpoint support; image input is a separate capability. See [OpenRouter's model catalog](https://openrouter.ai/models).

Checkpoint-2 HTTP extraction uses that same live configuration. In mock mode, uploads never fabricate approved financial records: extraction fails visibly with `live_model_required`. Offline history and single-document expected-output imports are separately labeled `fixture_history` and `fixture_expected` and are restricted to explicit demo use.

Live mode does not silently fall back to mock fixtures. The provider transport is tested with mocked responses; no actual paid provider call has been validated in this repository's recorded checkpoint results.

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
| GET | `/api/alerts` | Persisted alerts; no anomaly detection runs at checkpoint 1 |

Money and quantities are decimal strings. List endpoints return `items`, `total`, `limit` and `offset`. Product errors use a versioned `error` object. A fresh database returns empty catalogs/lists and a typed restaurant-not-configured response until configured or explicitly seeded.

Well-formed requests to reserved dashboard, forecast, coverage-write, alert-acknowledgement and chat routes return **HTTP 501** until their implementation checkpoint. They do not return fabricated financial results. The legacy workbench's `/api/run` and `/api/stream` remain separate from business-data chat.

Uploads return HTTP 202; poll the document detail for `completed`, `needs_review` or `failed`. Exact-byte duplicates return the existing ID, while different bytes with an existing invoice/receipt business key enter review. Images are labeled as visual evidence, without claiming an independent OCR quote check. See [checkpoint 2](docs/checkpoint-2.md) for supported formats, limits, corrections, retry and offline examples.

Authoritative handoff artifacts:

- [Exported OpenAPI schema](docs/openapi.json)
- [Frontend TypeScript contracts](frontend/src/marginguard-api.ts)
- [Actual seeded read-response examples](examples/api)
- [Checkpoint 1 review checklist](docs/checkpoint-1.md)
- [Checkpoint 2 upload/review checklist](docs/checkpoint-2.md)

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

Recorded checkpoint-2 verification: **180 backend tests passed**, **3 frontend parser tests passed**, production build and dependency consistency passed. Live HTTP checks verified upload, explicit mock failure, manual review approval, byte-identical deduplication, source retrieval and unchanged future-feature boundaries. The full v2 history passed schema/business validation and atomic import tests. The test-client dependency emits one deprecation warning. Actual paid model extraction remains unverified until a key/model is configured.

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
    import_demo.py           Explicit validated full-history fixture importer
    fixture.py               Explicit offline single-document demonstration
    seed.py                  Opt-in fictional seed CLI
frontend/src/
  App.tsx                    Existing generic workbench
  marginguard-api.ts          Product TypeScript contracts
docs/                        Plan, progress, review guide and OpenAPI export
examples/                    Canonical document pairs and API examples
demo_data/                   Team-contributed demo corpus
scripts/                     Setup, development launcher and contract exporter
tests/                       Database, API, contract and provider tests
data/                        Local runtime database; excluded from Git
```

## Scope and disclosure

The local application has no production authentication or deployment configuration. Model-supported interpretations and exact source matches do not establish that a business conclusion is correct. Planned cost projections describe ingredient consumption under stated assumptions, not actual net profit or a purchasing cash budget.

The reusable starter was prepared before the event. See [PREEXISTING.md](PREEXISTING.md) for the preparation inventory and disclose it accurately during judging. Preserve the distinction between fictional fixtures, recorded test results and functionality built during each checkpoint.
