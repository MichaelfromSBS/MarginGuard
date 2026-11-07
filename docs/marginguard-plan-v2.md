# MarginGuard v2 — receipts, costs, forecasts, chat and proactive alerts

NOVA 2026 · DoorDash Back of House · Team requirements revision · November 7, 2026

This supersedes the narrower invoice-only plan in `marginguard-plan.md`. It is a project plan, not a statement that these features already exist. The repository currently provides the generic React/FastAPI/OpenRouter starter.

## Product and five required capabilities

**MarginGuard turns incoming supplier invoices and customer sales receipts into an automatically maintained restaurant ledger, explains current performance, projects next month's sales and ingredient costs, and alerts the owner to meaningful changes with supporting evidence.**

| Team requirement | Planned behavior | Visible result |
| --- | --- | --- |
| Supplier invoices → dish costs and next-month cost | Extract and normalize ingredient prices; join to recipes and forecast demand | Price history, current recipe costs, projected ingredient requirement and cost |
| Customer receipts → sales, revenue and next-month sales | Extract completed sales and items; aggregate by date/dish/channel; calculate a demand baseline | Actual units and net item revenue; next-month units and revenue projection |
| Owner asks questions | Model selects validated read-only metric tools; Python queries and calculates; model explains returned results | Answer cards with period, coverage, source references and assumptions |
| Owner does not ask | Persistent worker processes newly uploaded/dropped files and updates derived state | Dashboard updates automatically; ingestion continues with the browser closed |
| Abnormalities trigger alerts | Python generates measurable findings; AI explains evidence and possible follow-up | Persistent in-app alert plus one external notification channel |

The owner does not need to start a chat to trigger processing. The model is not the financial calculator or an independent source of sales forecasts.

## MVP scope

One restaurant, one currency, three dishes, a small ingredient catalog, and in-store/delivery channels. All fictional demo records and fee assumptions are labeled. Import readable PDFs and clean PNG/JPEG receipt or invoice images. Readable PDFs use local text extraction; images use a vision-capable model. Unsupported/scanned PDFs enter review rather than being silently treated as successfully read.

All five capabilities above are in scope. Keep each narrow:

- One reliable extraction schema per document type, with suggested known catalog IDs.
- One transparent sales forecasting method, not an LLM prediction or a large ML system.
- A few database-backed chat intents rather than arbitrary SQL or arbitrary business tasks.
- Four initial alert types rather than unrestricted anomaly claims.
- In-app notifications plus a Discord webhook for the external notification demonstration. If the webhook is unavailable, the in-app alert remains visible; do not claim a phone notification was delivered.

Defer payout reconciliation, live POS/platform/email integrations, actual inventory accounting, staffing, automatic repricing, outgoing supplier messages and a general-purpose autonomous agent. Supplier drafts and the previous price what-if screen become optional after the team's five requirements work.

## Required setup data

Invoices and receipts alone do not establish recipe costs. Seed or configure:

1. **Ingredient catalog:** canonical ingredient IDs, aliases and base units.
2. **Menu catalog:** canonical dish IDs and effective selling prices per channel.
3. **Recipes:** ingredient quantities per dish, with compatible units and effective versions.
4. **Channel assumptions:** packaging and optional simplified fee rules for contribution estimates.
5. **Business calendar and data coverage:** open/closed dates and whether each day/channel's receipt import is complete, partial or unknown.

AI may suggest a mapping from a source description to a catalog item. Unknown descriptions, modifiers not represented in a recipe, missing package weights and ambiguous matches enter a review queue. A low-confidence-looking self-reported score is not a substitute for validation.

Invoice changes update ingredient costs, not menu selling prices. Receipt data can show realized unit-price changes; configured menu prices and discounts distinguish a true list-price change from a promotion.

## 1. Ingest invoices and sales receipts

Two input routes feed the same persisted processing queue:

- Upload through the dashboard, selecting Invoice or Sales receipt.
- Drop into `inbox/invoices/` or `inbox/receipts/`, watched by the worker.

Selecting the type avoids unnecessary document-classification uncertainty. Save source files under generated names and retain source/page/line references. Use only necessary receipt fields; the prototype does not need customer names, addresses or payment-card details.

Invoice fields: vendor, invoice number, invoice date, currency, item description, quantity, purchase unit, pack size, unit price, line total and document total.

Receipt fields: receipt/order ID, local sale timestamp, channel when known, currency, completion/void/refund status, item description, quantity, gross item amount, allocated discount, net item amount, tax, tip and charged total. Never guess an absent channel; store unknown and expose that coverage limit.

Use schema-constrained model output, then verify business rules in Python. Preserve originals alongside parsed records. Validate compatible units/currency, line arithmetic and document reconciliation. Define document-level discount allocation explicitly: proportional to eligible gross item values, rounding residual cents allocated deterministically so item totals reconcile. For the six-hour demo, use standard completed receipts with no discounts; uncommon adjustment formats enter review.

Statuses: Detected → Processing → Completed, Needs review or Failed. Valid records update automatically. Ambiguous records are persisted but do not contribute to approved financial metrics until corrected/approved.

The same file hash is a no-op. A different file with the same normalized vendor/invoice key, or the same channel/receipt key, becomes a possible revision/duplicate for review rather than a second purchase or sale. A customer receipt and platform export for the same order must not be counted twice. Explicit void/refund documents must be linked and modeled or sent to review; never count them as fresh positive sales.

## 2. Maintain sales and cost metrics

Use Decimal-compatible strings at extraction boundaries and Decimal or integer minor units in financial code. Record the currency, rounding policy and calculation version. Use ROUND_HALF_UP for displayed cents while preserving adequate unit-cost precision; historical totals must reconcile to source amounts under the documented allocation rules.

Core observed metrics:

- Units sold, order count, net item revenue and average net item revenue per order.
- Breakdown by completed local day, dish and known channel.
- Ingredient unit-price history with originating invoice lines.
- Current theoretical recipe cost and optional channel contribution.

Definitions:

`net item revenue = gross item sales - recognized discounts - recognized item refunds`

Exclude sales tax and tips from this metric. It is not a platform payout, bank deposit or net profit. If refunds/discounts are unsupported or not fully imported, say so and restrict the reported coverage accordingly.

`ingredient unit cost = attributable invoice line cost / total compatible base units`

`recipe cost = sum(recipe ingredient quantity × selected ingredient unit cost)`

For the MVP, normalized ingredient costs exclude freight, purchase tax and other unallocated invoice charges. Compare the same canonical ingredient and currency; do not interpret a package-size or product-grade change as a like-for-like price spike.

Store effective-dated ingredient prices and recipes. Current replacement-cost estimates use the latest approved price as of the calculation date. An older invoice arriving late extends history without overwriting the current price. Updating today's price does not rewrite actual historical financial results. Optional reconstructed historical recipe costs must be labeled theoretical and use prices available as of each sale date.

Purchases are separate from consumption. The prototype cannot derive actual cost of goods sold, inventory on hand or actual profit from invoices and receipts alone.

## 3. Project next calendar month's sales and ingredient cost

Produce explicit values for units, net item revenue, ingredient quantities and ingredient consumption cost. "Next month" means the next calendar month in the restaurant timezone. From a November 7, 2026 snapshot, that is December 1–31, 2026, not the next 30 days.

For an eight-week demo history, use a **weekday-average demand baseline**:

1. Aggregate approved receipts into complete local days by dish and channel.
2. For each weekday, average units across up to the preceding eight comparable complete weeks.
3. Predict each open date next month using its corresponding weekday average; explicitly configured closed dates have zero projected demand.
4. Sum daily projections into dish/channel/month totals, then aggregate to restaurant totals so every view reconciles.

The demo eligibility policy requires at least four complete observations of each applicable open weekday. This is a configurable product guardrail, not a statistical guarantee. Sparse dish/channel series show insufficient history rather than an invented forecast. With insufficient coverage, allow a clearly labeled user-entered planning scenario, but do not label it a historical-data forecast.

Unknown or partial days are not zero-sales days. Require a closed-day record or completion marker, provided by a completed import batch or owner confirmation, to distinguish zero sales from missing receipts. Actual sales-so-far update immediately with every valid receipt. Demand forecasts use complete days; a newly imported partial day need not change the forecast until its coverage is complete.

Revenue projection:

`projected revenue = sum(projected dish/channel units × assumed net selling price)`

For the demo with no discounts, use configured current channel menu prices. If forecasting with promotions, use an explicit expected discount assumption rather than silently treating gross menu price as net revenue. Do not let a price-change scenario alter demand unless a separate demand-response model exists.

Cost projection:

`projected ingredient requirement = sum(projected dish units × recipe ingredient quantities)`

`projected ingredient consumption cost = sum(projected ingredient requirement × current normalized ingredient prices)`

The baseline holds supplier prices and recipe quantities constant. It excludes inventory already held, wastage, purchase timing, package-order rounding, labor, rent and other expenses. Consequently this is an ingredient-consumption cost projection, not total business expense or an invoice/purchasing cash budget. Display ingredient quantities to make the connection inspectable.

Show base and configurable lower/higher demand scenarios, for example ±15% volume. Label these **sensitivity scenarios**, not 80%/95% prediction intervals. Record method, training window, data cutoff, coverage, forecast horizon, source data version and price snapshot. Refresh affected projections after approved changes; show stale/recalculating status until the new snapshot is ready.

Evaluation: with enough complete history, withhold the final seven days, fit only on earlier data and compare unit MAE against a seasonal-naive baseline (same weekday one week earlier). Do not tune against the withheld period, claim monthly predictive accuracy from a seven-day test, or present synthetic-data performance as real-world validation. More advanced models and calibrated intervals are future improvements.

## 4. Database-backed owner chat

The owner can ask:

- "What were net sales last week, and which dishes sold most?"
- "How has the beef price changed?"
- "What is the Classic Burger's ingredient cost now?"
- "What are next month's projected revenue and ingredient cost?"
- "Why did the cost projection increase?"
- "Which alerts need my attention?"

Route questions to a small tool catalog:

| Tool | Validated arguments | Returned information |
| --- | --- | --- |
| `get_sales_summary` | date range, optional dish/channel | units, revenue, orders, completeness and receipt references |
| `get_ingredient_history` | canonical ingredient, date range | normalized prices, changes and invoice references |
| `get_dish_cost` | dish, as-of date, optional channel | recipe inputs, selected prices and calculated contribution assumptions |
| `get_month_forecast` | horizon, optional dish/channel | persisted forecast values, method, scenarios, version and coverage |
| `explain_forecast_change` | two snapshot IDs | volume effect, price effect, joint effect and source changes |
| `get_alerts` | status and optional type | measured findings, evidence, review status |

The model selects tools and writes explanations. Backend code owns queries, date interpretation validation, arithmetic and result IDs. No arbitrary generated SQL, code execution or chat-driven database writes. Limit tool steps and returned rows. Clarify genuinely ambiguous dates or requests rather than returning an answer for an arbitrary period.

Show deterministic metric cards next to narrative answers. Every material numeric claim references a returned metric or evidence record. Show as-of time, requested period, data coverage, and whether a value is observed, modeled or projected. Unsupported questions return a specific limitation. No database upload or vector database is necessary for these structured metrics.

For explaining changes in `cost = volume × unit recipe cost`, compare saved snapshots and calculate effects in code: volume effect at old cost, price effect at old volume, and the interaction term when both change. Sum them to the total difference; do not attribute all cost growth to supplier prices when sales volume also changed.

## 5. Proactive evidence-backed alerts

After each approved import or review correction, update the relevant actuals/prices, run applicable checks and invalidate/recompute affected projections. No owner prompt is required. The alert subsystem combines measured findings with AI explanation; it is not an unconstrained LLM scanning an entire database and declaring anomalies.

Initial rules below are configurable **demo policies**, not universal restaurant thresholds:

| Alert | Example trigger | Required evidence and gate |
| --- | --- | --- |
| Ingredient price spike | Comparable normalized price rises >10% | Old/new invoice lines, dates, pack conversion and computed percent |
| Material cost projection increase | Repricing the same demand snapshot raises monthly ingredient cost by >$50 | Fixed demand version, changed ingredients, affected dishes and exact cost difference |
| Unusual sales day | Complete-day units are >30% below the prior comparable-weekday mean and the difference is at least 10 units | Complete-day status, observed units, previous comparable days; require four earlier complete observations |
| Data-quality exception | Conflicting duplicate, unresolved unit/mapping or totals mismatch | Document IDs and specific failed validation; label as data quality, not a proven financial loss |

Run price checks immediately on approved invoices. Evaluate complete-day sales alerts only once coverage is complete, not at lunch against full-day totals. Do not silently delete unusual days from forecasts; flag them and show any explicit owner-approved exclusion with a reason.

Each alert contains type, severity, event time, period, measured change, comparison basis, source references, calculation version and a suggested investigation. AI may explain plausible causes but must distinguish a hypothesis from a measured fact. A sales drop is not proof of why customers bought less; a supplier price rise is not proof of an invoice error.

Persist New / Acknowledged / Resolved states. Update the existing alert when its evidence changes; do not create another alert on every dashboard refresh. Use event keys and a persisted notification outbox. A committed alert survives model-wording or webhook failure; deterministic wording is the fallback. Track attempted/sent/failed notification status and bound retries. Do not promise exactly-once webhook delivery.

## Architecture and data model

Keep the existing React/TypeScript + FastAPI + OpenRouter foundation. Add SQLite, a PDF text extractor, and a persistent Python worker. Use ordinary Python forecasting code; a new agent framework, vector store or task broker is unnecessary for the local MVP.

```text
Dashboard uploads / watched invoice and receipt folders
                         ↓
          Persisted queue and ingestion worker
                         ↓
      AI extraction + mapping → validation/review
                         ↓
     Approved invoice/receipt records in SQLite
                         ↓
   Sales aggregates + price history + recipe costs
                         ↓
    Forecast snapshots + anomaly/event detection
                  ↙                    ↘
    Dashboard and chat tools       Alerts + notification outbox
```

Do model calls outside database write transactions. Use short transactions for approved ledger updates and durable recomputation jobs. Derived results carry a source data version; never present an old forecast as current after a newer import. The worker resumes pending jobs after restart, persists import deduplication, and does not depend on an open browser session.

| Table/group | Key content |
| --- | --- |
| documents / processing_jobs | type, hash, source path, status, validation errors and timestamps |
| invoices / invoice_lines | normalized vendor/invoice key, date, structured fields, source line references |
| ingredients / ingredient_prices | catalog, units, effective date, normalized price and invoice provenance |
| dishes / menu_prices / recipe_versions | canonical menu, channel prices and effective recipe ingredient quantities |
| receipts / receipt_items | unique order key, local date, status, dish mapping and reconciled amounts |
| daily_coverage / daily_sales | date/channel completeness and derived approved aggregates |
| forecast_runs / forecast_values | horizon, method, source version, assumptions, projected units/revenue/ingredient costs |
| alerts / notification_outbox | event key, findings, evidence, acknowledgement and delivery state |

Suggested modules: `ingestion.py`, `extraction.py`, `db.py`, `economics.py`, `forecasting.py`, `chat_tools.py`, `detectors.py`, `notifications.py`, plus `backend/worker.py`. Both document routes share queue, validation, provenance and deduplication infrastructure.

Suggested API contracts:

- `POST /api/documents` — enqueue an invoice or receipt upload.
- `GET /api/documents` and `GET /api/documents/{id}` — processing and review status.
- `POST /api/documents/{id}/review` — save validated corrections and trigger recomputation.
- `POST /api/coverage/complete` — mark a date/channel or completed batch as complete.
- `GET /api/dashboard` — actual sales, current costs, forecast and coverage metadata.
- `GET /api/forecasts` and `GET /api/alerts` — persisted evidence-backed results.
- `POST /api/chat` — validated read-only metric tools and grounded response.
- `POST /api/alerts/{id}/acknowledge` — record an owner action without changing the underlying financial facts.

## Dashboard

Four compact views are enough:

1. **Overview:** actual net item revenue/units for a chosen period, current dish costs, next-month revenue/cost projections, and unresolved alerts. Observed and projected cards are visually distinct.
2. **Documents:** invoice/receipt uploads, processing status, extracted line items, source previews and Needs review.
3. **Trends and outlook:** ingredient prices, complete-day sales, next-month demand/revenue/ingredient requirement and sensitivity scenarios.
4. **Ask MarginGuard:** questions and source-linked metric cards; the relevant alert can open directly into its evidence.

Include last updated time, data coverage and source links in context. In-app alerts should appear within the same interface without an owner question; the external notification is supplemental.

## Demo data and checked example

Use fictional Tartan Burger Co., three dishes, and eight weeks of completed historical receipt records and supplier prices. Seed the historical ledger through a documented structured fixture import; do not claim hundreds of historical receipts were OCR-processed during the live demo. Live-process at least one real fixture PDF invoice and one fixture receipt image or PDF through the actual model path.

For Classic Burger, retain the verified economics: 0.50 lb beef, other ingredients $1.60, selling price $12.00, beef $4.00 → $4.72/lb. Recipe cost is $3.60 → $3.96. A fictional 30% delivery fee and $0.60 packaging give contribution $4.20 → $3.84.

If the next-month demand baseline projects **1,200 Classic Burgers**, then:

| Value for Classic Burger only | Before new invoice | After new invoice |
| --- | --- | --- |
| Projected units | 1,200 | 1,200 |
| Projected item revenue, no discounts | $14,400 | $14,400 |
| Projected beef requirement | 600 lb | 600 lb |
| Projected ingredient consumption cost | $4,320 | $4,752 |

The price-only cost increase is **$432** at the same projected demand. The invoice does not itself change demand or selling prices. Have the actual forecasting code compute units from the seed data; 1,200 is an illustrative fixture target, not an output to hard-code.

Example alert: "Beef rose 18%, from $4.00 to $4.72/lb. At the current 1,200-burger demand projection, Classic Burger's next-month ingredient cost increases $432. Sources: prior/new invoice lines and forecast snapshot. Assumptions: unchanged demand, recipe and supplier price for the projection horizon."

Negative controls: same unit price with a different pack size; identical receipt reimport; incomplete current day with only a few receipts; unknown dish; an old invoice arriving late.

## Three-minute demonstration

| Time | Action and outcome |
| --- | --- |
| 0:00–0:25 | Establish the owner problem; show approved history, coverage and December forecast |
| 0:25–0:55 | Upload a customer sales receipt; its actual items/units/revenue enter the database and dashboard without a chat prompt |
| 0:55–1:40 | Drop a new beef invoice; show normalized price, affected recipe costs, refreshed price-only cost projection and proactive alert |
| 1:40–2:15 | Ask "Why did next month's ingredient cost increase?" Chat retrieves the versioned evidence and calculated $432 example |
| 2:15–2:40 | Open the source line/calculation; acknowledge the alert; show notification state |
| 2:40–3:00 | Reimport the receipt or show the package-size negative control; explain forecast assumptions and integration boundary |

Keep a labeled recording of a real successful run as a backup. Fixture/mock mode and actual model-assisted processing must remain distinguishable.

## Two-person, six-hour build sequence

| Time, November 7 Eastern | Teammate A: ingestion/backend | Teammate B: analytics/UI | Shared checkpoint |
| --- | --- | --- | --- |
| 11:00–11:30 | Agree schemas and get one invoice/receipt extraction working | Agree fixtures, metric definitions and forecast method | Both document types parse representative examples |
| 11:30–1:00 | Database, queue, both extraction schemas, normalization/deduplication | Weekday baseline and core dashboard against fixed contract | Both sides can run independently on agreed fixtures |
| 1:00–2:00 | Integrate actuals/prices and refresh jobs | Connect current metrics and forecast cards | Both document types update persisted metrics end to end |
| 2:00–3:00 | Metric tool endpoints and anomaly rules/outbox | Chat interface/tool selection, evidence and alert presentation | All five requirements work in a narrow integrated flow |
| 3:00–4:00 | Error handling, restart/deduplication and notification checks | Forecast holdout, coverage/assumption labels and negative controls | Acceptance cases pass; no invented empty-data predictions |
| 4:00–5:00 | Rehearse, capture backup and prepare submission together | Fix demo-critical issues and polish together | Working demo preserved before deadline |

This is more ambitious than v1. Save time by keeping the five capabilities simple: fixed catalog, basic statistical forecast, six chat tools, four alert types and one notification channel. Cut decorative charts, free-form chat expansion, supplier drafting, what-if pricing, complex models and live integrations before dropping a required capability. If the integrated loop is late, stop adding variants and focus on one invoice, one receipt, one forecast question and one valid alert.

## Acceptance criteria

1. A valid invoice updates the correct ingredient price and dish recipe costs; package-unit conversions are correct.
2. A valid receipt updates the right date/dish/channel units and net item revenue exactly once, with source reconciliation.
3. Both imports work while the browser is closed; reopening shows persisted state.
4. The illustrative burger fixture produces $3.96 recipe cost and, for 1,200 projected units, $4,752 ingredient cost and a $432 price-only difference.
5. Forecasts use only approved complete past days, target the correct next calendar month, and aggregate consistently across dishes/channels.
6. Insufficient history or incomplete coverage produces an explicit limitation; missing receipts are not treated as zero demand.
7. Chat returns database-calculated figures with period, as-of time, coverage, forecast/actual labels and valid evidence IDs; unsupported questions do not invent statistics.
8. Valid anomaly findings create one persistent alert with reproducible calculations; duplicate imports and worker restarts do not repeatedly create the same event.
9. Complete-day sales alerts do not fire solely because the current day or channel import is partial.
10. Bad arithmetic, ambiguous mappings, unsupported credits or unreadable documents enter review without contaminating approved totals or financial alerts.
11. AI-wording or webhook failure leaves the underlying alert intact and its notification state visible.
12. Forecast evaluation uses a held-out period and reports MAE; sensitivity scenarios are not mislabeled as calibrated prediction intervals.

## References and boundaries

Simple forecast baselines and held-out evaluation are established forecasting practices; the weekday-average method, data thresholds and anomaly rules above are explicit MVP design choices. Future work should measure forecast quality on real restaurant data before claiming predictive reliability.

- [Forecasting: Principles and Practice — benchmark methods, evaluation and intervals](https://otexts.com/fpp3/toolbox.html)
- [OpenRouter structured output support](https://openrouter.ai/docs/guides/features/structured-outputs)
- [DoorDash reporting terminology and payout distinctions](https://merchants.doordash.com/en-us/learning-center/payout-and-monthly-statement)

Describe live integrations as future work requiring appropriate access and merchant authorization. Disclose the generic pre-event starter accurately and label synthetic data. Subscription value, customer adoption and savings are hypotheses to validate, not established demo outcomes.
