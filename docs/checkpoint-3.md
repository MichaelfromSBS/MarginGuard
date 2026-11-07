# Checkpoint 3 — observed sales, dish costs and forecasts

Backend implementation is ready for team review. The frontend still contains the generic starter workbench; the routes below are ready for the restaurant dashboard teammate. No model calls or new dependencies are required for checkpoint 3. Extraction continues to use the existing `.env` configuration.

## Start against your existing checkpoint-2 database

Stop the backend with Ctrl+C and restart it in the **same PowerShell window** to preserve its process-level database selection:

```powershell
cd "E:\CMU\Sophomore\Fall\NOVA Hackathon"
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Startup applies additive migration 3. It does not reset or seed your database, reprocess documents, or change `.env`. A new terminal instead uses `.env`/its own environment; select the same database explicitly when using a new terminal. Do not point it at the three-receipt checkpoint-1 seed and expect a historical forecast.

For a completely separate offline baseline, create a uniquely named database. Use this only when you want an isolated demo rather than the already ingested records:

```powershell
$checkpoint3Db = "data/checkpoint3-$(Get-Date -Format 'yyyyMMdd-HHmmss').db"
.\.venv\Scripts\python.exe -m backend.marginguard.import_demo --database $checkpoint3Db
$env:MARGINGUARD_DATABASE_PATH = $checkpoint3Db
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

## Copyable review commands

In a second PowerShell window:

```powershell
$base = "http://127.0.0.1:8000"
Invoke-RestMethod "$base/api/health"

$sales = Invoke-RestMethod "$base/api/sales?start=2026-10-31&end=2026-11-06&as_of=2026-11-07"
$sales | Select-Object orders, units, net_revenue, average_order_revenue
$sales.by_dish | Format-Table
$sales.coverage | Select-Object status, complete, partial, unknown, closed

$cost = Invoke-RestMethod "$base/api/dishes/classic_burger/cost?as_of=2026-11-07"
$cost | Select-Object dish_id, ingredient_cost, source_data_version
$cost.ingredients | Format-Table ingredient_id, quantity, base_unit, unit_cost, extended_cost
$cost.channels | Format-Table

$forecast = Invoke-RestMethod -Method Post "$base/api/forecasts/recalculate" `
    -ContentType "application/json" -Body '{"as_of":"2026-11-07"}'
$forecast | Select-Object id, status, method, source_data_version
$forecast.horizon
$forecast.metrics | Format-Table id, value, unit
$forecast.ingredients | Format-Table
$forecast.scenarios | Format-Table
$forecast.evaluation

$dashboard = Invoke-RestMethod "$base/api/dashboard?as_of=2026-11-07"
$dashboard.metrics | Format-Table id, value, kind, coverage
```

Expected with full v2 history:

| Check | Before the live beef invoice | After it is approved |
| --- | --- | --- |
| Oct 31–Nov 6 orders | 332 | 332 |
| Oct 31–Nov 6 net item revenue | $7,400.00 | $7,400.00 |
| Classic Burger replacement ingredient cost | $3.60 | $3.96 |
| December projected net item revenue | $31,286.93 | $31,286.93 |
| December projected ingredient consumption cost | $9,413.63 | $10,143.80 |

The invoice's price-only monthly cost difference is $730.17 with unchanged projected demand. A November 7 receipt adds its observed sales immediately but does not become a finished complete training day. Repeating the forecast request with the same policy/date/source version returns the same saved run.

To verify an invoice or receipt change, calculate a forecast, approve the document using checkpoint 2, and inspect the saved forecast:

```powershell
Invoke-RestMethod "$base/api/forecasts/$($forecast.id)" |
    Select-Object id, status, source_data_version
```

It becomes `pending`, with its original values and source version preserved. POST the same recalculation request again to create the updated snapshot. Automatic recomputation without an API request belongs to checkpoint 4.

## API handoff

| Route | Response / behavior |
| --- | --- |
| `GET /api/sales` | Observed totals, day/dish/channel breakdowns, completeness and up to 20 source references |
| `GET /api/dishes/{dish_id}/cost?as_of=YYYY-MM-DD` | Replacement recipe cost, ingredient quantities/prices/invoice references and channel contribution assumptions |
| `GET /api/dashboard` | Actual/modeled metric cards, sales summary, all dish costs, most recent forecast for the as-of date, up to 20 persisted alerts and limitations |
| `POST /api/forecasts/recalculate` | Synchronous deterministic calculation and atomic saved snapshot; no AI request |
| `GET /api/forecasts?limit=50&offset=0` | Newest saved snapshots first, with explicit stale/pending status |
| `GET /api/forecasts/{run_id}` | One saved snapshot with daily/series projections, ingredient requirements, scenarios and evaluation |
| `POST /api/coverage/complete` | Explicit owner/importer confirmation that a finished local date/channel is complete, or a channel is closed |

Sales and dashboard query arguments: `start`, `end`, `as_of`. Dates are inclusive; at most 366 days. Default sales period is the seven finished local dates preceding `as_of`, which defaults to today in the restaurant timezone. Sales can include the current as-of day explicitly, but dates beyond it are rejected. `/api/sales` additionally accepts `dish_id` and `channel_id`. Group order counts count distinct matching receipts; orders across dishes are not additive because one receipt can contain several dishes. `by_day` contains observed-sale dates; completeness rows identify explicit zero/closed/missing dates.

Forecast request fields are optional:

```json
{
  "as_of": "2026-11-07",
  "history_weeks": 8,
  "min_observations": 4,
  "sensitivity_pct": "15"
}
```

The window is 4–26 weeks; required observations are at least four and no more than the window length. Sensitivity is a decimal string from 0 through 100 percent. Monday is weekday 0, Sunday 6. Every series exposes the exact training sample dates used for each weekday. Unit averages use eight decimals; money rounds half up to cents and deterministic residual-cent allocation reconciles row totals.

Coverage confirmation example, **only after confirming the entire past day/channel was imported**:

```powershell
Invoke-RestMethod -Method Post "$base/api/coverage/complete" `
    -ContentType "application/json" `
    -Body '{"date":"2026-11-06","channel_id":"in_store","status":"complete"}'
```

Identical confirmation is a no-op. A change is audited in `coverage_events`, increments the restaurant data version, and invalidates forecasts. You cannot confirm the current/future local day as complete or close a day/channel with approved sales. A future channel closure is allowed and affects the horizon. Calendar-closed dates cannot be confirmed complete through this endpoint. Missing coverage rows are synthesized as `unknown` in summaries, with the query time as their `updated_at`; this does not create persisted completion records.

## Calculation boundaries

- Actual net item revenue sums approved completed receipt item net amounts, with allocated discounts already applied. Tax and tips are excluded. Refunds/voids and unresolved documents are not treated as ordinary completed sales.
- Recipe cost uses compatible base units and the latest approved effective invoice price on or before the as-of date. Same-date prices resolve by latest document creation time, then insertion order. Future-dated prices are ignored. An older invoice extends history without replacing a newer effective price.
- Forecasts use only complete days strictly before the as-of date. Explicit closed days, missing/unknown days and partial days are excluded. A confirmed complete day without receipts contributes zero units only for dishes already offered according to effective menu prices and recipes.
- Each applicable open weekday needs at least four samples per dish/channel. Missing history, recipes or prices are reported in per-series limitations. The top-level `insufficient_history` state also covers missing required planning inputs. No partial restaurant forecast totals are published as complete; totals are null until every series is ready. An entirely closed horizon has zero demand.
- The horizon is the next calendar month in the restaurant timezone. Explicit calendar/channel closures have zero demand; unconfigured future dates assume open, as disclosed. Prices and current recipes stay fixed; discounts and demand response are not predicted.
- Ingredient quantities represent projected consumption, not a purchase order or inventory balance. Contribution estimates omit labor, rent and other overhead. None of these figures represent actual profit.
- The final seven past local days are withheld for evaluation. The weekday mean fits only earlier days and is compared with the same weekday one week earlier. MAE is per dish/channel/day on matched complete observations. Partial evaluation samples are labeled; synthetic results do not establish real-world accuracy.
- Persisted runs retain their exact calculation payload, price/source references, source version, assumptions and training dates. `forecast_runs.status` is the authoritative freshness state; old calculation JSON is immutable. A `pending` run's values describe an older snapshot and must not be rendered as a current forecast.

Forecast calculation does not make model calls. A key is required only when testing actual document extraction. Read-only business chat, automatic recalculation/notifications and the independent worker remain checkpoints 4–5.

## Automated verification

```powershell
.\.venv\Scripts\python.exe -m pytest -q
npm.cmd run typecheck
npm.cmd run test:frontend
```

The tests use isolated databases and explicit fixtures/mocked extraction; they do not reset the configured business database or spend API credits. OpenAPI is exported in `docs/openapi.json`; frontend interfaces are in `frontend/src/marginguard-api.ts`.
