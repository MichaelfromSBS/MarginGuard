# MarginGuard — revised hackathon plan

Superseded by [MarginGuard v2](marginguard-plan-v2.md), which incorporates invoice and sales-receipt ingestion, next-month forecasts, database-backed chat and proactive alerts. This document preserves the earlier invoice-only scope.

NOVA 2026 · DoorDash Back of House fallback · November 7, 2026

This is an implementation plan. The existing workspace is a generic AI starter; the restaurant workflow described here has not yet been built.

## Pitch and customer

**MarginGuard watches incoming supplier invoices, connects ingredient-price changes to menu items, and helps restaurant owners decide how to respond.**

The initial user is an owner-manager of one restaurant with a small menu and limited time to review invoices. The business hypothesis is that catching an actionable cost change early and quantifying its impact saves enough management time and contribution dollars to justify a subscription. A demo alone does not validate willingness to pay.

The core product interaction is:

**Invoice arrives → identify and normalize ingredients → detect a meaningful change → recalculate affected dishes → alert with evidence → compare a response.**

The application owns ingestion, history, calculations, alerts and decisions. AI handles varied invoice language and suggests ingredient mappings. Deterministic code controls financial results and scenario calculations.

## MVP boundary

Build one restaurant, three dishes, two channels, a small predefined ingredient catalog and readable invoice PDFs. All restaurant records and fee assumptions are fictional and labeled as such.

| Must ship | Defer |
| --- | --- |
| Background invoice-folder watcher | Live Toast, DoorDash or email connections |
| Readable PDF text extraction and structured AI parsing | Scanned PDFs, OCR and arbitrary document formats |
| Ingredient mapping with review for ambiguity | General supplier-catalog matching |
| Unit-normalized price-change detection | Payout reconciliation and disputes |
| Recipe and channel contribution calculations | Inventory valuation, actual P&L, labor and waste accounting |
| Alert with source and calculation evidence | General financial chat |
| Delivery-price what-if comparison | Demand forecasting, staffing and automatic repricing |
| Draft supplier clarification message | Sending supplier messages or changing an actual menu |

Discord notification is a stretch goal after the in-app workflow works. A notification is a delivery mechanism, not the central product capability.

## Exact demo dataset

Restaurant: **Tartan Burger Co.** Supplier: **Ridgeline Foodservice**. Both fictional.

Use a small baseline price history from three earlier invoices and seven days of fictional sales to supply an explicit constant-volume scenario. Additional history is optional and should not consume the build window.

| Input | Value |
| --- | --- |
| Previous ground-beef unit price | $4.00/lb |
| New unit price | $4.72/lb, an 18% increase |
| Beef per Classic Burger | 0.50 lb |
| Other ingredient cost per Classic Burger | $1.60 |
| Classic Burger price | $12.00 in both channels |
| Delivery fee assumption | 30% of item price; fictional scenario assumption |
| Delivery packaging | $0.60 per burger |
| In-store packaging assumption | $0.00 for this simplified demo |

Derived results, calculated by code:

| Metric | Before | After |
| --- | --- | --- |
| Beef cost per burger | $2.00 | $2.36 |
| Total recipe cost | $3.60 | $3.96 |
| Ingredient-only margin | 70% | 67% |
| Delivery contribution per burger | $4.20 | $3.84 |
| In-store contribution per burger | $8.40 | $8.04 |

Use **200 Classic Burgers sold in the preceding seven days**, split 80 in-store and 120 delivery. Holding that volume and mix constant, the new ingredient cost reduces estimated weekly contribution for this dish by **$72.00**. Of that, **$43.20** is from delivery orders.

The alert can say:

> Ground beef increased 18%, from $4.00 to $4.72/lb. Classic Burger delivery contribution falls from $4.20 to $3.84 per order. At last week's unchanged volume, this dish would generate $72 less contribution over seven days. Review the invoice and compare a response.

Use the same beef quantity in a Cheeseburger recipe to demonstrate one ingredient affecting multiple dishes. Keep Veggie Burger unaffected to demonstrate selective recalculation. The $72 figure above covers Classic Burger only; any combined exposure must be computed from both dishes' actual fixture quantities.

Do not label these numbers net profit, realized loss, recovered savings or a demand forecast. They are replacement-cost contribution estimates under explicit assumptions. A new invoice does not establish that previously sold burgers used ingredients at the new cost.

## What the owner sees

One main screen is enough:

1. **Watchdog status:** running, last scan, file currently processing and last completed import.
2. **Current economics:** each dish's contribution per channel, the calculation basis and included/excluded costs.
3. **Alert inbox:** impact-ranked alerts with New / Reviewed / Resolved states.
4. **Evidence detail:** original invoice line, parsed package, normalized cost, ingredient mapping and affected recipe quantities.
5. **Response comparison:** delivery-price adjustment and its calculated contribution impact.

For the what-if example, increase Classic Burger's delivery price from $12.00 to **$12.50**. With the demo's 30% fee and unchanged recipe/packaging costs:

`12.50 - 3.75 - 3.96 - 0.60 = 4.19`, displayed as **$4.19**.

The improvement relative to the new $3.84 contribution is **$0.35/order**, or **$42.00 across 120 delivery orders**. This almost restores the old $4.20 delivery contribution; it does not offset the in-store impact. Show prominently that volume is held constant and customer demand response is not modeled. The price is a scenario, not an automatic recommendation or live menu update.

The owner may mark an alert reviewed, record a decision, and generate a supplier clarification draft with invoice number, item, old/new comparable unit prices and the observed difference. The draft is presented for review and is not sent by the application. It must not allege a billing error merely because a price increased.

## Processing and financial rules

**Invoice parsing:** extract vendor, invoice number, invoice date, currency, item descriptions, quantities, unit/pack size, unit prices and line totals. Preserve each original source line. A schema-valid model answer is still untrusted until business validation passes.

**Mapping:** provide the model a small canonical ingredient catalog. It can suggest a catalog ID or return unresolved. Unknown ingredients, conflicting mappings, missing pack weights and inconsistent amounts become Needs review; they do not update costs or create financial conclusions. Do not treat model-generated confidence scores as calibrated accuracy.

**Normalization:** initially support lb, oz and cases with explicit package weights, plus each for countable ingredients. Do not convert each to weight without a known conversion. For beef, compare dollars per pound:

`normalized unit price = attributable line cost / total pounds`

For the demo, line cost excludes sales tax, freight and other charges; state this limitation. Only compare equivalent catalog ingredients and currencies. Quantities and unit prices must be positive; totals must reconcile within a documented rounding tolerance. Unsupported credit/revision documents go to review rather than being forced through ordinary purchase logic.

**Price changes:** compare with the preceding approved price by invoice date, not merely the last file ingested. An older invoice arriving late should extend history without replacing the current price. Trigger a price-change alert above a configurable 10% threshold; use the threshold only as a demo policy, not an industry standard. Show absolute per-serving impact and estimated exposure, and rank by that exposure. Do not use an unexplained universal 60% margin threshold.

**Contribution:** calculate item revenue minus theoretical recipe cost, packaging and the configured channel fee. The demo has no discounts, refunds, tax allocations or fixed per-order fees. Store the fee basis and inclusion assumptions rather than implying this models every platform's terms.

**Precision and history:** parse monetary values as Decimal-compatible strings; use Decimal in calculations. Retain sufficient precision for unit costs and recipes, calculate aggregate scenarios before rounding, and use an explicit ROUND_HALF_UP display policy. Preserve historical price versions. Current replacement-cost scenarios and historical records are separate concepts; the prototype does not claim actual historical profitability.

## Architecture and extension of the starter

Use the existing **React/TypeScript + FastAPI** starter rather than introducing a second frontend stack. Add **SQLite**, a small PDF text-extraction library, and a separate Python worker. Model access stays behind the existing server-side OpenRouter adapter, with model ID configurable in `.env`.

The PDF path is `readable PDF → local text extraction → structured model call`. Raw PDF input is not assumed to be natively supported by the chosen model. Scanned/empty documents produce a clear unsupported-input/review state. Benchmark the extraction model on the actual fixtures before committing to it; upgrading the model is a configuration choice.

```text
inbox/ → worker → extraction + validation → SQLite
                     ↓                      ↓
                 review queue       price/recipe calculations
                                            ↓
                                     persistent alerts
                                            ↓
                               FastAPI → React dashboard
                                            ↓
                             what-if calculation / draft
```

The worker polls about every two seconds. It calls the model only for a new eligible document, never on every poll. It keeps operating when the browser closes. The dashboard polls a read endpoint for updates and never starts another watcher when a user opens a tab.

Suggested additions to the existing repository:

```text
backend/
  marginguard/
    db.py          # database setup and short-lived connections
    ingestion.py   # file state, PDF text and processing orchestration
    extraction.py  # prompt/schema, validation and ingredient mapping
    economics.py   # unit conversions, recipe costs and scenarios
    detectors.py   # price-change alerts and impact ranking
    actions.py     # supplier clarification draft
  worker.py        # persistent folder watcher
data/
  menu.csv
  recipes.csv
  channel_rules.csv
  sales.csv
  marginguard.db    # generated local runtime data; exclude from source control
inbox/
demo_invoices/
tests/
  test_economics.py
  test_ingestion.py
```

Suggested data entities:

| Entity | Essential fields |
| --- | --- |
| Imported file | SHA-256, path, status, error, processing timestamps |
| Invoice and lines | normalized vendor ID, invoice number/date, source text, extracted amounts |
| Ingredient and price version | canonical ID, base unit, normalized price, effective date, source line |
| Recipe and channel terms | ingredient quantities, menu price, fee basis/rate, packaging |
| Sales | dish, channel, date, quantity |
| Alert | unique event key, source price change, affected items, impact, status |
| Decision | alert ID, chosen scenario or note, timestamp |

Processing requirements:

- Read only stable files; copying a temporary file and atomically renaming it into `inbox/` is the preferred demo procedure.
- Persist states such as Detected / Processing / Needs review / Completed / Failed.
- Reimporting identical bytes is a no-op. A different file sharing vendor and invoice number becomes a possible revision/duplicate for review; do not double-count it.
- Commit approved data and its alert event atomically. Do not hold a database write transaction open during a model call.
- Persist alert uniqueness, so a worker restart or browser refresh cannot create another in-app alert for the same event.
- Use bounded request timeouts and retries. The demo can manually retry failed imports; no unbounded retry loop.
- A notification/AI-summary failure must not discard a valid alert. A deterministic alert template is sufficient for the MVP; optional AI wording cannot change its calculated values.
- If Discord is added, track delivery separately from alert creation. Avoid claiming exactly-once webhook delivery; keep the in-app alert as the reliable source of state.

## Three-minute demo

| Time | What to show |
| --- | --- |
| 0:00–0:20 | Owner problem and fictional restaurant; explain the cost assumptions |
| 0:20–0:40 | Baseline menu economics and watcher status |
| 0:40–1:20 | Drop the beef invoice; show processing, new alert and affected dishes |
| 1:20–1:45 | Inspect the source line and unit conversion behind the result |
| 1:45–2:20 | Test the $12.50 delivery-price scenario; show recalculated contribution and assumptions |
| 2:20–2:40 | Generate the supplier clarification draft or record an owner decision |
| 2:40–3:00 | Reimport the invoice: no duplicate event. Explain the package-size negative control and integration boundary |

Prepare the package-size negative-control fixture even if it is shown only during questions: after the new price is $4.72/lb, replace two 10-lb cases at $47.20 each with one 20-lb case at $94.40. Total weight and normalized price are unchanged, so no price-spike alert is appropriate despite the doubled per-case price.

Do not spend the demo waiting for network delivery to a phone. Keep a clearly labeled recording of a real successful run as a backup, and distinguish fixture mode from an actual model-assisted run.

## Six-hour build sequence

All times November 7, Eastern. Lunch is inside the hacking window; protect integration time and take breaks in turns if useful.

| Time | Teammate A | Teammate B | Exit condition |
| --- | --- | --- | --- |
| 11:00–11:30 | Check model/key; freeze input/result contracts together | Agree screen layout and fixtures together | One real extraction succeeds; expected fixture math is fixed |
| 11:30–1:00 | SQLite, normalization, economics, ingestion | Product UI against the agreed fixed JSON contract | Worker produces persisted valid data; UI displays complete fixture workflow |
| 1:00–2:00 | Connect import and alert endpoints | Connect UI to API and refresh | Real invoice updates the screen end to end |
| 2:00–3:00 | Review queue, duplicate handling, edge-case checks | Evidence view and price-scenario interaction | Complete invoice → evidence → decision workflow |
| 3:00–3:45 | Run regression fixtures and fix calculation/import issues | Finish supplier draft or decision recording; improve errors | Must-have acceptance cases pass |
| 3:45–4:15 | Optional Discord only if the core is stable | Visual clarity and labels | No new core features |
| 4:15–5:00 | Rehearse, capture backup and prepare disclosure together | Submission and final smoke check together | Working demo preserved before deadline |

**Cut line:** if no integrated invoice → alert workflow works by 2 PM, stop adding features. Prioritize ingestion, correct math, evidence and the what-if interaction. Drop supplier drafting and Discord first.

## Acceptance cases

1. The actual demo invoice produces $4.72/lb and an 18% increase, with the correct source line.
2. Classic Burger recipe cost changes $3.60 → $3.96, delivery contribution $4.20 → $3.84, and constant-volume exposure equals $72 for 200 burgers.
3. The $12.50 delivery-price scenario shows $4.19/order and $42.00 total improvement for 120 delivery orders.
4. Veggie Burger remains unchanged.
5. A same-unit-price package-size change produces no price-spike alert.
6. Reimport and worker restart do not duplicate approved prices or alert events.
7. Unknown ingredient, missing pack weight, inconsistent totals or unreadable PDF produces Needs review rather than a financial conclusion.
8. An old invoice arriving late does not overwrite the current replacement price.
9. Model/network failure is visible and retryable; existing dashboard data remains usable.
10. With the browser closed, a new valid invoice is still processed; reopening shows the persisted alert.

## What to claim and what to validate later

Claim a working local prototype with continuous folder monitoring, model-assisted invoice interpretation, deterministic cost impact and an inspectable owner decision workflow. Describe live provider integrations as future work requiring suitable access, exports and merchant authorization. Existing products already cover much of restaurant back-office accounting; this prototype's chosen focus is the short invoice-change-to-decision interaction, not category novelty.

Next customer-validation questions: Which invoice changes do owners currently miss? Who maintains recipes and portion quantities? Can owners obtain usable sales exports? Is alert accuracy sufficient to change purchasing/pricing decisions? Does the workflow save enough time or money to merit payment?

Disclose the generic starter and any materials prepared before the event according to the organizer rules. Label all fictional data and modeled assumptions. Record what the team actually built during the event.

References checked during planning:

- [DoorDash payout reporting](https://merchants.doordash.com/en-us/learning-center/payout-and-monthly-statement)
- [DoorDash Marketplace API access](https://developer.doordash.com/en-US/docs/marketplace/faq/getting_started/)
- [Toast standard API access](https://support.toasttab.com/en/article/Standard-API-Access)
- [Existing category example: MarginEdge](https://www.marginedge.com/)
- [OpenRouter structured outputs](https://openrouter.ai/docs/guides/features/structured-outputs)
