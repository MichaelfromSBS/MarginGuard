# Checkpoint verification guide

Which demo inputs to use at each checkpoint, and the exact result to expect. All numbers come from `answer_key.md`.

## 1. Database and API contract
**Load:** `config/*` + `seed/*` (no AI calls).
**Verify:**
- 3 dishes, 9 catalog ingredients (7 used in recipes; fryer oil and takeout bags are non-recipe).
- 2,752 receipts / 3,687 receipt lines; 28 voided + 23 refunded.
- Coverage: Oct 14 = missing, Nov 7 = partial, every other day Sep 12 – Nov 6 = complete.
- 8 history invoices; current beef price $4.00/lb.
- The frontend can render every endpoint from this seed alone. That makes it a good fixture for mock responses.

## 2. Document ingestion
**Use:** `documents/live_demo/` 1, 2, 3 (happy path), then 4, 5, 6. Compare each extraction with `expected_extractions.json`.
**Verify:**
- Receipt 1: 2 × Classic Burger + 1 × Side of Fries, in_store, items $28.50, tax $2.00, tip $5.00, total $35.50.
- Invoice 2: beef qty 2, case 10 lb, $47.20/case → **$4.72/lb**; buns 2 × $24.00.
- Receipt 3 (PNG): chicken sandwich + burger, delivery, coupon −$2.00, total $22.47.
- Receipt 4 (re-import of 1): **rejected as duplicate**; row counts unchanged.
- Invoice 5: 3 lines → Needs review (missing case weight, unknown "MICROGREENS MIX", 3 × $12.00 ≠ $39.00).
- Receipt 6: unknown dish "Mushroom Swiss Burger" → Needs review.
- Extra check: run `documents/history_invoices/INV-30407_2026-10-27.pdf` through extraction. Its 20 LB case at $80 must normalize to **$4.00/lb**.

## 3. Metrics and forecasting
**Verify against the answer key:**
- Classic Burger cost $3.60 → $3.96 after invoice 2. Chicken $2.60, Fries $0.80 (unchanged).
- Last 7 complete days (Oct 31 – Nov 6): 321 orders, $5,925.00 net revenue, $18.46/order.
- December: 30 open days; Classic Burger ≈ 1,189.2 units; projected revenue $26,156.71 (low $22,233.20 / high $30,080.21).
- December ingredient cost $6,945.63 → $7,373.73 (+$428.10). Beef requirement ≈ 594.6 lb.
- **Missing data:** Oct 14 excluded from weekday averages, not counted as 0. Nov 7 partial is excluded from the forecast.
- Backtest MAE (units/dish/day): weekday average 5.84 vs previous-week 7.05.

## 4. Background processing and alerts
**Do:** start the worker, then drop files into the watched folders. Don't use the chat.
**Verify:**
- Startup: exactly **1** alert, the unusual sales day for Thu Nov 5 (−56.1%). **No** alert for Nov 7 (partial) or Oct 14 (missing).
- After invoice 2: beef price alert (+18.0%) and projected-cost alert (+$428.10). Restarting the worker creates **no** new copies.
- After invoice 5 / receipt 6: one data-quality alert each.
- No alert for the Oct 27 20 lb case or for the tomato drift.
- Notification failure: blank out `DISCORD_WEBHOOK_URL` and re-run. The alert must still be stored, with delivery state = failed.

## 5. Database-backed chat
| Question | Expected answer contains |
|---|---|
| What were sales in the last 7 complete days? | $5,925.00, 321 orders, Oct 31 – Nov 6 (observed) |
| Which dish sold the most? | Classic Burger, 256 units (same period) |
| How has the beef price changed? | $4.00 → $4.72/lb, INV-30440, Nov 7 |
| What does the Classic Burger cost now? | $3.96 (was $3.60) |
| What are next month's projected revenue and ingredient cost? | $26,156.71 revenue; $7,373.73 cost (projected, Dec 1–31) |
| Why did the cost projection increase? | beef +$0.72/lb × ≈594.6 lb = +$428.10, citing INV-30440 |
| Which alerts need attention? | the open alerts list |
| *Unsupported:* What will my rent be? / Delete last week's sales | declines; read-only; no data for this |
