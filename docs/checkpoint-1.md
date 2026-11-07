# Checkpoint 1 — database foundation and shared contract

Historical checkpoint record. Checkpoint 2 implements ingestion/review, and checkpoint 3 implements metrics/forecasting. Use [checkpoint-2.md](checkpoint-2.md), [checkpoint-3.md](checkpoint-3.md) and the current OpenAPI for the latest behavior.

Checkpoint 1 establishes the persistent data model, validated schemas, explicit fictional seed data and frontend API shapes. It does not implement document ingestion, PDF/image extraction, financial analytics, forecasting, a background watcher, notification delivery or business-data chat.

## Run and configure

From the project root on Windows:

```powershell
python scripts/setup.py
.\.venv\Scripts\python.exe -m backend.marginguard.seed
npm run dev
```

Stop development servers before rerunning setup. On macOS/Linux, use `.venv/bin/python` for explicit virtual-environment commands. Open `http://127.0.0.1:8000/docs` for the current OpenAPI contract and `http://127.0.0.1:5173` for the existing starter UI. Checkpoint 1 does not replace that UI with a restaurant dashboard.

The root `.env` is local and ignored by Git. Leave `AI_MODE=mock` until a later checkpoint requires a real model. Insert the team key into `OPENROUTER_API_KEY` and a compatible model ID into `OPENROUTER_MODEL` when ready; do not put either into frontend code or `VITE_*` settings. Database and catalog inspection must work with no key.

Starting the API initializes the database schema but does not silently seed fictional financial records. Seed data is opt-in using the command above. Repeating it should be a no-op, and the seed command must not mix demo records into a nonempty, unseeded business database.

## Implemented read surface

- `GET /api/capabilities` — API version `1.0.0`, checkpoint number and explicit feature availability.
- `GET /api/restaurant` — configured restaurant and demo identity; an empty database has no configured restaurant.
- `GET /api/catalog` — ingredient/dish/channel catalog, menu prices and recipes.
- `GET /api/ingredients/{ingredient_id}/prices` — effective-dated ingredient price records and originating invoice-line IDs.
- `GET /api/documents` — paginated document metadata and processing state, without full source text.
- `GET /api/documents/{id}` — document detail with the same metadata plus nullable persisted `source_text` for evidence inspection.
- `GET /api/invoices` — approved seeded invoice records and lines.
- `GET /api/receipts` — approved seeded receipt records and items.
- `GET /api/coverage` — explicit local date/channel completeness records.
- `GET /api/alerts` — persisted alert records; an empty list does not imply anomaly checks have run.

Paginated list responses use `{ "items": [], "total": 0, "limit": 50, "offset": 0 }` (the limit value reflects the request/default). Catalog is a distinct object with `source_data_version`, `is_demo`, `ingredients`, `dishes` and `channels`; dishes contain nested `prices` and `recipes`, and recipes contain ingredient `items`. Ingredient price history is a separate paginated route. The exact filters, defaults and error shapes are defined by generated OpenAPI. Money and quantities are JSON decimal strings; the frontend must not assume every financial field is a JavaScript number.

The schema includes later-stage entities such as forecast runs, alerts and notification delivery state so future checkpoints have a stable place to persist their results. Empty tables are not fabricated forecasts or successful notification results.

Future product routes for uploads/review, coverage writes, dashboard analytics, forecasts, chat and alert acknowledgement are reserved with explicit 501 Not Implemented responses until their corresponding checkpoint. A frontend should show a future-feature state or use a separately labeled mock; it should not interpret a 501 response as real zero revenue or zero projected cost. Upload's reserved contract uses multipart form fields `document_type` (`invoice`/`receipt`) and `file`; the expected extraction JSON in `examples/` is not the upload request body.

Product errors use `{ "api_version": "1.0.0", "error": { "code": "...", "message": "...", "details": {} } }`. Render the readable message, and use the stable code to distinguish not-yet-implemented, not-found and validation states. The generic starter's existing endpoints remain a separate interface; the new TypeScript definitions are in `frontend/src/marginguard-api.ts`.

For a quick contract review in PowerShell:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/capabilities | ConvertTo-Json -Depth 8
Invoke-RestMethod http://127.0.0.1:8000/api/catalog | ConvertTo-Json -Depth 12
Invoke-RestMethod 'http://127.0.0.1:8000/api/documents?limit=2&offset=0' | ConvertTo-Json -Depth 8
Invoke-RestMethod http://127.0.0.1:8000/api/ingredients/beef/prices | ConvertTo-Json -Depth 8
```

Catalog entries use stable IDs such as `beef`, `classic_burger`, `in_store` and `delivery`. A price-history item includes `id`, `ingredient_id`, `invoice_line_id`, `effective_date`, decimal-string `unit_cost` and `base_unit`. Invoice/receipt read responses add persistent IDs to the extraction structure and nest their `items`; receipt records additionally contain `local_date`.

Share the exported [OpenAPI contract](openapi.json), [TypeScript types](../frontend/src/marginguard-api.ts), and actual seeded JSON examples in [examples/api](../examples/api). The example files cover restaurant, catalog, documents, invoices, receipts, coverage, ingredient prices, alerts and capabilities. They are generated against an isolated seeded database, not copied from an owner's live data. Regenerate through `scripts/export_contract.py` when intentionally changing the contract.

## Fictional seed expectations

The seed restaurant is Tartan Burger Co., USD, America/New_York. Known channels are `in_store` and `delivery`. The catalog includes beef, bun, produce, cheese and veggie patty, plus Classic Burger, Cheeseburger and Veggie Burger recipes.

The sample price history contains beef at $4.00/lb and later $4.72/lb. The other canonical ingredient costs are bun $0.60/each, produce $1.00/each, cheese $0.40/each and veggie patty $1.60/each. Menu prices are Classic Burger $12.00, Cheeseburger $13.00 and Veggie Burger $11.00. The delivery fee/packaging records are explicit simplified fictional assumptions, not platform pricing claims.

Seeded records are synthetic database fixtures. They must not be presented as outputs of a real invoice model call. The small foundation seed is not an eight-week forecasting dataset, and no prediction is produced from it in this checkpoint.

## Review checklist

1. Start without an API key; inspect `/docs` and the read routes.
2. Inspect the empty-database behavior before opting into demo data.
3. Run the seed command twice; confirm IDs and counts do not grow on the second run.
4. Confirm foreign keys reject references to nonexistent documents, dishes or ingredients.
5. Confirm business duplicate keys and document hashes cannot silently duplicate records.
6. Check the persisted quantities and amounts against the seed's source text and expected arithmetic.
7. Restart the server; confirm data persists rather than being regenerated on each request.
8. Check future endpoints return explicit 501 responses and the API does not claim forecasting or ingestion is implemented.
9. Give the teammate [sample-data-contract.md](sample-data-contract.md) and the paired files in `examples/` before generating PDFs or receipt images.
10. Keep `.env`, local database files and generated source documents out of Git; commit only intentional synthetic fixtures and source code.

## Next checkpoints

Checkpoint 2 turns invoice/receipt uploads into validated persisted records. Checkpoint 3 implements metrics and forecasting. Checkpoint 4 adds the independent worker, anomaly checks and notification state. Checkpoint 5 provides read-only database-backed chat. Each checkpoint should end with a runnable result and a focused review before proceeding.
