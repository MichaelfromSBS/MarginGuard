# MarginGuard — demo inputs (NOVA 2026)

All data is **fictional**: restaurant *Tartan Burger Co.*, suppliers *Ridgeline Foodservice* and *Allegheny Produce Co.*
Every document is marked "DEMO DATA". Generated before the hacking window — disclose as prepared demo data.

Snapshot date: **Saturday, Nov 7, 2026**. Forecast month: **December 2026**.

## Folder map
```
config/                         restaurant setup (load once)
  ingredient_catalog.csv        9 ingredients: id, name, base unit, used_in_recipes, aliases for matching
  recipes.csv                   3 dishes × ingredients × qty per dish
  menu_prices.csv               selling price per dish per channel (in_store, delivery)
  restaurant_calendar.csv       open/closed days Sep–Dec (closed Nov 26, Dec 25)
  demo_policy.json              tax, alert thresholds, forecast settings
seed/                           history already "approved" (load at startup — no AI calls needed)
  historical_receipts.csv       2,752 receipts Sep 12 – Nov 7 11:30 (completed / voided / refunded)
  historical_receipt_lines.csv  dishes on each receipt (linked by receipt_id)
  import_coverage.csv           per-day status: complete / missing (Oct 14) / partial (Nov 7)
  historical_invoice_extractions.json   the 8 history invoices as structured data
documents/
  history_invoices/             the same 8 invoices as PDFs (optional: run them through real extraction)
  live_demo/                    files to drop in during the demo, numbered in demo order
expected/
  answer_key.md                 every number the app should show (prices, costs, forecast, alerts, backtest)
  expected_metrics.json         key numbers in machine-readable form (for tests)
  expected_extractions.json     correct extraction for each live document (for testing the AI extractor)
```

## Live demo files (in order)
| # | File | What it tests | Expected result |
|---|---|---|---|
| 1 | `1_receipt_R-20261107-0006.pdf` | Receipt → sales, no prompt | +$28.50 revenue, 2 burgers + fries |
| 2 | `2_invoice_INV-30440_beef_increase.pdf` | Price increase, package conversion ("2 CASES, 10 LB EACH") | Beef $4.00 → $4.72/lb; 2 alerts; Dec cost +$428.10 |
| 3 | `3_receipt_R-20261107-0007_photo.png` | Image input | +$21.00 revenue (delivery, coupon) |
| 4 | `4_receipt_R-20261107-0006_REIMPORT.pdf` | Duplicate | Not counted again |
| 5 | `5_invoice_APC-7781_needs_review.pdf` | Review queue | 3 issues → Needs review + data-quality alert |
| 6 | `6_receipt_R-20261107-0008_unknown_item.pdf` | Unknown dish | Needs review; not counted |

Core demo from the spec uses 1 → 2 → (ask the chat) → 4. Files 3, 5, 6 are extra proof points.

## Planted situations in the history
- **Oct 14:** receipt import missing → must be excluded, not treated as zero sales.
- **Oct 27 (INV-30407):** beef sold as a 20 LB case at $80 → still $4.00/lb, must NOT alert.
- **Tomato:** small drift ($2.00–$2.10/lb) → below threshold, no alert.
- **Thu Nov 5:** sales −56% vs previous Thursdays → unusual-sales-day alert at startup.
- **Nov 7:** partial day (imported to 11:30) → must NOT trigger a low-sales alert.
- 28 voided + 23 refunded receipts → excluded from revenue.

## Definitions used in the answer key
- **Net item revenue** = item amounts − discounts, completed receipts only (no tax, tips, voids, refunds).
- **Unit price** = case price ÷ case contents in base unit (e.g. "6/5 LB CASE" = 30 lb).
- **Forecast** = mean units per weekday by dish and channel over complete days in the last 8 weeks × December open days; low/high = −15% / +15%.
- **Projected ingredient cost** = projected units × recipe qty × current unit price.
