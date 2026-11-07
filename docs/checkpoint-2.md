# Checkpoint 2 — document ingestion and review

Implemented: readable PDF and PNG/JPEG uploads, structured OpenRouter extraction, deterministic validation, review/correction, duplicate-safe ledger approval, source inspection, retry and explicit offline fixture/history import. The teammate's restaurant frontend is now integrated: use Inbox for uploads/status/source inspection/retry, or `/docs` and the commands below for full manual-review API checks.

This is the ingestion review guide. Checkpoint 3 adds [sales summaries, recipe costs and forecasts](checkpoint-3.md); checkpoint 4 adds the [independent worker and in-app alerts](checkpoint-4.md). At the current checkpoint, the upload API enqueues durable jobs. Run `npm.cmd run dev` or start `python -m backend.worker` alongside the API to process them. Business-data chat remains checkpoint 5.

## Configure and start

Install the updated lockfile with `python scripts/setup.py` after stopping development servers. Keep the root `.env` local and ignored:

```dotenv
AI_MODE=openrouter
OPENROUTER_API_KEY=your-team-key
OPENROUTER_MODEL=your-compatible-model-id
MARGINGUARD_DATABASE_PATH=data/demo-v2.db
MARGINGUARD_UPLOAD_DIRECTORY=data/uploads
MARGINGUARD_EXTRACTION_MAX_OUTPUT_TOKENS=6000
AI_TIMEOUT_SECONDS=60
```

Use a model endpoint supporting structured output, and image input for PNG/JPEG. Restart after configuration or Python changes. The two main demo PDFs have passed live extraction with Gemini 3.8 Flash; image extraction has not yet been live-verified. `/api/health` reporting `configured: true` means that configuration is present, not that a provider request has succeeded.

The provider schema omits the item array's `maxItems: 200` constraint because Gemini rejected that extraction request with HTTP 400. The original Pydantic schema still enforces the 200-item maximum, along with all financial and source-evidence checks, before persistence.

For the full fictional history, explicitly initialize a **fresh** database first:

```powershell
.\.venv\Scripts\python.exe -m backend.marginguard.import_demo --database data/demo-v2.db
```

This validates and imports eight invoice fixtures and 2,733 receipt fixtures, their source evidence, catalogs, calendar and coverage. It makes no model calls, records `fixture_history` provenance, commits atomically, and refuses to mix with the small checkpoint-1 seed. Repeating the identical corpus import is a no-op; altered input requires a different fresh database. Set `.env` to this database before serving it.

Alternatively keep the existing checkpoint-1 seeded database for small upload tests. The migration to schema 2 preserves its records. Never import both histories into one ledger.

Start the backend:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Open [interactive API docs](http://127.0.0.1:8000/docs). Use `npm run dev` instead if both frontend and backend should start; do not start a second server on an occupied port.

## Upload and poll

```powershell
curl.exe -X POST http://127.0.0.1:8000/api/documents -F "document_type=receipt" -F "file=@demo_data/live_demo/1_receipt_TB-20261107-001.pdf;type=application/pdf"
```

The response is HTTP 202 with the document ID. Poll `GET /api/documents/{id}` for the final state. Browser requests can observe `detected`, then `processing`, then a terminal state. The response header `X-MarginGuard-Duplicate` indicates whether the bytes already existed; duplicates reuse the existing ID and do not trigger another model call.

- `completed`: approved invoice/receipt lines and effective prices are persisted atomically.
- `needs_review`: extracted content has issues; no part of that document enters the approved ledger.
- `failed`: provider/configuration/network/processing failure; the reason is visible and retryable.

Repeat for `live_demo/2_invoice_RF-20261107-004.pdf` with `document_type=invoice`, or `live_demo/3_receipt_TB-20261107-002_photo.png` with `document_type=receipt` and `type=image/png`.

Limits: readable PDFs at most 4 MB, 10 pages and 64,000 extracted characters; PNG/JPEG at most 3 MB and 20 million pixels. Unsupported media/MIME mismatches are rejected before registration. Scanned, encrypted or malformed PDFs require review/re-export; an unreadable source cannot be approved merely by posting expected JSON.

## Inspect, review and retry

`GET /api/documents/{id}` adds these fields to the existing metadata:

- `extraction`: persisted structured extraction, when available.
- `validation_issues`: stable codes, messages and optional zero-based item indices.
- `page_count`, `source_text`, `evidence_mode` and `extraction_method`.
- `reviewed_at` and `review_note`.

`GET /api/documents/{id}/source` serves the saved upload. Its bytes must match the recorded SHA-256. Historical bulk fixtures have persisted source text but no uploaded binary; their source route returns a typed unavailable response.

For readable PDFs, item quotations are checked against the specified page after whitespace normalization. This checks text membership, not complete semantic correctness. Image evidence is labeled `visual`; its transcription has not been independently OCR-verified.

Correct a reviewable or failed document with `POST /api/documents/{id}/review`:

```json
{
  "document_type": "receipt",
  "extraction": { "...": "the full corrected ReceiptExtraction object" },
  "note": "Reviewed against the uploaded original."
}
```

Use the actual full schema from OpenAPI or the paired expected examples; the abbreviated object above is explanatory, not executable. Corrections pass the same arithmetic/catalog/source checks, are recorded in the review history, and cannot overwrite an already-approved ledger entry. Conflicting business keys must be resolved as distinct valid source records; clicking review does not bypass duplicate protection. No endpoint creates new catalog ingredients/dishes automatically.

After a transient failure or server restart, use `POST /api/documents/{id}/process` to retry the saved file. Requests already active in this process cannot be retried or reviewed concurrently. Completed documents cannot be reprocessed into another entry. At this checkpoint pending/stale jobs are resumed manually; there is no independent restart-resuming worker yet.

If a document failed before the Gemini schema fix, restart the server in its existing terminal to keep the same process environment/database selection, then retry its existing ID. Uploading identical bytes again only returns the existing failed document; it does not retry extraction. There is no need to reset or reimport the database.

## Offline demonstration without an API key

In `AI_MODE=mock`, HTTP uploads do not invent approvals. A readable upload becomes `failed` with `live_model_required`; its source can still be inspected and manually reviewed against a supplied correction.

For explicitly fictional demo databases only, this command supplies expected extraction JSON directly while exercising the real reader, business validation and approval transaction:

```powershell
.\.venv\Scripts\python.exe -m backend.marginguard.fixture --database data/demo-v2.db --type invoice --file demo_data/live_demo/2_invoice_RF-20261107-004.pdf --expected demo_data/live_demo/2_invoice_RF-20261107-004.expected.json
```

It labels the result `fixture_expected`, makes no model call, and is not an HTTP-sidecar fallback. It refuses non-demo restaurants. Do not present this path or `fixture_history` as measured AI extraction accuracy.

## Validation and state changes

- Invoice/receipt line arithmetic, totals, quantities, discounts and catalog references are checked with Decimal.
- Case sizes must be explicit; lb/oz conversion is supported and count-to-weight guesses are blocked.
- Voids/refunds and unknown channels/items are reviewed instead of counted as ordinary completed sales.
- Identical hashes reuse the document; different bytes with the same normalized invoice/receipt business key enter review.
- Every approval increments the restaurant data version and writes a durable data-change record. Existing ready forecast snapshots become pending, but no forecast is calculated yet.
- New receipt input marks the date/channel partial, including backfilled days that had previously been called complete. Full-history import sets coverage explicitly only after all its records pass validation.
- Ingredient price versions are effective-dated; late invoices extend history without overwriting the newest date's price.

## Review checklist

1. Inspect `/api/capabilities`: ingestion, metrics and worker/alerts are implemented; business chat is not. `/api/worker` reports whether the worker is actually running.
2. Load v2 history into a fresh database twice; check eight invoices/2,733 receipts and no second import.
3. Upload the main receipt and invoice with an actual configured model, or use the explicitly labeled offline fixture path.
4. Reimport the receipt's exact duplicate bytes; verify the same ID and unchanged sales/version.
5. Process E2 after the main invoice: different total/same business key must remain in review.
6. Process E3: normalized beef price stays $4.72/lb despite a changed case size.
7. Process E4/E4b: ambiguous supplier/item/case or unknown dish must not affect approved financial rows.
8. Correct a missing receipt channel through review; confirm approval and an immutable review record.
9. Retry a failed provider call; confirm at most one ledger entry.
10. Process E5 late invoice; the latest effective beef price remains $4.72/lb.

## Windows PDF checkout fix

The committed v2 PDFs were valid. Git's automatic LF-to-CRLF conversion changed their byte offsets in the Windows worktree, causing strict PDF parser failures. `.gitattributes` now marks PDF/image files as binary data for line-ending handling. The affected local PDF copies were restored byte-for-byte from their committed blobs; business content was not regenerated or changed.

If an older checkout already has converted PDF bytes, save any intentional document edits first, then restore the relevant tracked PDF files from Git after pulling the attributes. Do not use a broad destructive reset on a working tree with changes.
