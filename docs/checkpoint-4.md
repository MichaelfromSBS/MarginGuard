# Checkpoint 4 — persistent worker and in-app alerts

Implemented: a separate persistent worker, automatic forecast refresh, two focused anomaly types, source evidence and in-app acknowledgement/resolution. Notifications stay inside the website. No external owner-message integration or webhook configuration is included.

The teammate's frontend wording files are unchanged. The existing alert list, bell counter and toast component consume the live alert API. Optional AI suggestions are available in the alert response for the frontend teammate to display.

## Start the application

Stop the old development command with Ctrl+C. Use the **same PowerShell window/database selection** you used for checkpoint 3:

```powershell
cd "E:\CMU\Sophomore\Fall\NOVA Hackathon"
npm.cmd run dev
```

This now starts **three processes**: API, independent worker and frontend. Open http://127.0.0.1:5173. Closing the browser does not stop ingestion or calculation. Ctrl+C in the launcher terminal stops all three.

Startup applies migrations through schema 5; it does not reset, seed or replay the configured ledger. Existing `.env` key/model/database values are preserved. A fresh terminal has its own environment; point `MARGINGUARD_DATABASE_PATH` at the same full v2-history database if you switch terminals.

For backend-only work, run the API and worker in separate terminals with the **same database/upload/inbox settings**:

```powershell
# API terminal
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

```powershell
# Worker terminal
.\.venv\Scripts\python.exe -m backend.worker
```

An upload now returns `detected` and a durable pending job. It needs the worker to advance to `processing`, then `completed`, `needs_review` or `failed`. Do not start a second worker for the same database. A database lease prevents two workers from running normally at once.

## Check status and drop an invoice

In a second PowerShell window:

```powershell
cd "E:\CMU\Sophomore\Fall\NOVA Hackathon"
$base = "http://127.0.0.1:8000"
Invoke-RestMethod "$base/api/health"
Invoke-RestMethod "$base/api/worker"
```

Health should show `checkpoint: 4`, `processing_mode: worker`, `worker: running`. `/api/worker` exposes heartbeat, queue/processing counts, new-alert count, watched-file errors and a safe error code. A successful API health response alone does not establish that the worker is running or the model is usable.

With the default inbox configuration:

```powershell
Copy-Item -LiteralPath "demo_data/live_demo/2_invoice_RF-20261107-004.pdf" `
    -Destination "inbox/invoices/live-invoice.pdf"
```

The worker creates the `inbox/invoices/` and `inbox/receipts/` folders. Place customer PDFs/photos in the receipts folder. Supported formats are the same bounded PDF/PNG/JPEG formats as uploads. The folder selects the document type; the model does not guess it. Original inbox files remain untouched.

After a file's size/mtime stays stable for the configured interval, the worker saves it through the same hash/queue/validation path as the upload API. A duplicate returns the existing document; it does not call the model or count money twice. A growing copy waits for another stable interval. Symlinks and unsupported suffixes are skipped; oversized files appear in the worker's watched-file error count.

Inspect the result:

```powershell
(Invoke-RestMethod "$base/api/documents?document_type=invoice&limit=100").items |
    Select-Object id, filename, status, error_code

$dashboard = Invoke-RestMethod "$base/api/dashboard?as_of=2026-11-07"
$dashboard.forecast | Select-Object id, status, source_data_version
$dashboard.forecast.metrics | Format-Table id, value

(Invoke-RestMethod "$base/api/alerts").items |
    Select-Object id, type, status, title, message
```

With the full history and the main invoice approved, December ingredient consumption cost becomes **$10,143.80**, from **$9,413.63**, and revenue stays **$31,286.93**. The worker calculates this without a chat question or Calculate button. The normal UI poll will pick up the result; source data remain versioned while recalculation is pending.

If the invoice is already approved in your database, copying it again is deliberately a no-op. Startup still detects its price/cost evidence if no corresponding alert already exists. Do not expect a new toast for an old known event.

## In-app notification behavior

`GET /api/alerts?status=new` is the persistent notification feed. The frontend's bell shows its total; its existing toast component announces newly observed alert IDs after the page's initial load. Alerts created while the browser is closed remain visible when it reopens. A toast is presentation, not the only copy of an alert.

```powershell
$newAlerts = (Invoke-RestMethod "$base/api/alerts?status=new").items
$newAlerts | Select-Object id, type, title

# Replace the ID with the alert you intend to acknowledge.
$alertId = "alert_id_from_the_list"
Invoke-RestMethod -Method Post "$base/api/alerts/$alertId/acknowledge"

# Optional: explicitly resolve a reviewed finding without changing ledger facts.
Invoke-RestMethod -Method Post "$base/api/alerts/$alertId/resolve"
```

The website's Acknowledge button uses the same endpoint. New/acknowledged/resolved states persist across worker/API/browser restarts. Financial data and evidence are not changed by acknowledgement. The earlier schema's `notification_outbox` table is retained to preserve immutable migrations, but is unused and stays empty; no external delivery process consumes it.

## Detection policies

The system creates only these two notification types:

| Finding | Gate | Evidence / timing |
| --- | --- | --- |
| Combined ingredient and overall cost increase | At least one consumed ingredient becomes more expensive **and** net projected ingredient consumption cost increases after cent rounding | One message names the rising ingredients, old/new prices, total monthly cost before/after and the net dollar increase. Same forecast demand is held fixed; offsetting ingredient decreases are included. No separate ingredient-price popup. |
| Yesterday's unusual sales | Yesterday is complete in every channel, with units **more than 30% below** the previous four complete matching weekdays, by **at least 10 units** | One dated report is issued on the next restaurant-local day. Includes yesterday's orders, units, net revenue, comparison basis and source references. No current-day, partial-day or older-day catch-up notifications. |

There is no 10% ingredient-price or $50 total-cost minimum. A smaller positive ingredient-driven overall cost increase also qualifies. An ingredient increase alone does not notify when total cost stays flat/falls, projected demand is zero, or required forecast inputs are missing. The cost describes projected ingredient consumption, not all business operating expense or actual profit.

A supplier-change notification is fixed to its first demand snapshot and deduplicated per source invoice, including across planning-month rollover. Repeated scans, same-price repacks, older late invoices and restarts do not create another event. Ingredient contributions reconcile to the displayed net increase, including offsets and residual-cent rounding.

Sales evaluation runs only for **yesterday** in the restaurant timezone. If coverage is incomplete at midnight, it can report later that same day after completion. Once the sale date is older than yesterday it is not newly reported. Existing reports remain in history until acknowledged/resolved, with absolute sale/report dates so their age is clear. Updated evidence can revise yesterday's finding; a no-longer-supported finding resolves. The existing 30%/10-unit sales-drop thresholds remain configurable demo policies.

Document parse/validation failures stay in Inbox and its review task; they do not create business alerts, bell increments or notification toasts.

Migration 5 archives the earlier separate ingredient-price, data-quality and backlog-style notifications before the API serves them. Their measured facts/evidence remain preserved as resolved history. Legacy type labels remain readable for those archive records; newly generated alerts use only `projected_cost_increase` and `unusual_sales` under `detectors_v2`.

For the demo baseline on **November 7**, no sales alert is generated: November 6 is yesterday and does not cross the rule. The November 5 anomaly is reported only on **November 6**: 24 orders, 39 units and $476.00 net sales, versus an 80.5-unit comparable-weekday mean (51.55% lower units). The answer key's roughly 51.3% figure is revenue-based. After the main beef invoice, exactly **one combined alert** explains that beef rose $4.00 → $4.72/lb and December projected ingredient cost rose $9,413.63 → $10,143.80 (+$730.17).

## AI and failure handling

AI extracts document language and optionally suggests an investigation step. Python owns measurements, thresholds, unit conversion and forecast effects. Alerts commit before optional wording runs. Supplementary suggestions cannot replace measured numbers; incomplete/invalid/model-failed wording keeps the deterministic suggestion and sets `explanation_status: fallback`.

Each alert adds `finding`, `suggestion`, `explanation_status`, `calculation_version` and `revision` to the existing message/evidence/state contract. The frontend can use these fields without changing numeric facts. A model suggestion is a possible follow-up, not a demonstrated cause.

Extraction uses cross-process job claims and completion fencing. Manual retry/review cannot race an active extraction lease. Transient provider failures receive exponential backoff, at most three attempts by default; permanent configuration/schema failures need correction and explicit retry. A normal cancelled extraction releases its claim. An abruptly killed process is recovered after leases expire (global worker lease 30 seconds; document claim timeout plus 60 seconds). Attempts survive interruptions, so repeated crashes do not reset the automatic attempt budget.

Source-data versions and the worker's saved cursor are durable recomputation triggers. After a restart, a newer ledger/coverage version or local date causes recalculation. Forecast cache keys prevent duplicate snapshots for the same inputs. A failed worker cycle leaves pending work durable and reports a safe error code rather than inventing a ready result.

Useful local settings, with defaults shown:

```dotenv
MARGINGUARD_PROCESSING_MODE=worker
MARGINGUARD_INBOX_DIRECTORY=inbox
MARGINGUARD_WORKER_POLL_SECONDS=2
MARGINGUARD_FILE_STABLE_SECONDS=2
MARGINGUARD_EXTRACTION_MAX_ATTEMPTS=3
MARGINGUARD_ALERT_AI_EXPLANATIONS=true
MARGINGUARD_SALES_DROP_PCT=30
MARGINGUARD_SALES_DROP_MIN_UNITS=10
```

`inline` processing is an explicit compatibility/test mode, not the default. Backend-only uploads in worker mode stay queued unless the independent worker is started. `python -m backend.worker --once` performs one bounded scan/process/recompute cycle; a fresh file with the normal stability delay may require a later cycle.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest -q
npm.cmd run build
npm.cmd run test:frontend
```

The automated worker tests use isolated databases and mocked extraction/wording, and exercise durable queues, bounded retries, claims, restart recovery, anomaly evidence, acknowledgement, correction and no external outbox activity. Existing schema versions 1–4 upgrade to version 5 while preserving records and retiring old notification-policy events. Detailed final verification is in [progress.md](progress.md).

Database-grounded owner chat remains checkpoint 5.
