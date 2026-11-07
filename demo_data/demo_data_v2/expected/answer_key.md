# MarginGuard demo data — answer key

Computed from `config/`, `history/` and the live/edge documents with exact decimals. All data is fictional.
Revenue = Σ item `net_amount` of completed receipts (excludes tax and tips). History has no discounts, voids or refunds.

## 1. Ingredient unit costs

| Ingredient | Base unit | History (weekly invoices Sep 15 – Nov 3) | Current before live demo | After RF-20261107-004 |
|---|---|---|---|---|
| beef | lb | 4.00 | $4.00 | $4.72 |
| bun | each | 0.6 | $0.60 | $0.60 |
| produce | each | 1, 1.05 | $1.00 | $1.00 |
| cheese | each | 0.4 | $0.40 | $0.40 |
| veggie_patty | each | 1.6 | $1.60 | $1.60 |

- Conversions: beef 10-lb case $40.00 → $4.00/lb; bun 48-each case $28.80 → $0.60; cheese 160-each case $64.00 → $0.40; veggie patty 24-each case $38.40 → $1.60; produce bought per each.
- Produce drifts $1.00 → $1.05 (Sep 29, Oct 6) → $1.00: +5%, below the 10% threshold.
- **Beef $4.00 → $4.72/lb (+18.00%)** on RF-20261107-004 (2 cases × 10 lb @ $47.20).

## 2. Dish ingredient cost

| Dish | Menu price | Cost before | Cost after | Cost % of price |
|---|---|---|---|---|
| Classic Burger | $12.00 | $3.60 | $3.96 | 30.0% → 33.0% |
| Cheeseburger | $13.00 | $4.00 | $4.36 | 30.8% → 33.5% |
| Veggie Burger | $11.00 | $3.20 | $3.20 | 29.1% → 29.1% |

Classic Burger: 0.50 × 4.72 + 0.60 + 1.00 = **$3.96** (contract's known answer).

## 3. Sales history

2733 completed receipts, Sep 12 – Nov 6. Coverage: every date/channel `complete` except **Oct 14 = unknown (both channels)**. Nov 7: in_store `partial`, delivery `unknown` (no history receipts on Nov 7).

| Week (Sun–Sat) | Orders | Net revenue | Classic | Cheeseburger | Veggie |
|---|---|---|---|---|---|
| Sep 06 | 60 | $1,305.00 | 47 | 35 | 26 |
| Sep 13 | 358 | $7,850.00 | 311 | 189 | 151 |
| Sep 20 | 343 | $7,091.00 | 263 | 202 | 119 |
| Sep 27 | 353 | $7,506.00 | 278 | 204 | 138 |
| Oct 04 | 346 | $7,667.00 | 276 | 214 | 143 |
| Oct 11 | 304 | $6,420.00 | 263 | 169 | 97 |
| Oct 18 | 361 | $7,770.00 | 307 | 195 | 141 |
| Oct 25 | 344 | $7,216.00 | 282 | 178 | 138 |
| Nov 01 | 264 | $5,932.00 | 220 | 172 | 96 |

**Last 7 complete days (Oct 31 – Nov 6):** 332 orders, $7,400.00 net revenue, $22.29 per order; in-store $4,315.00, delivery $3,085.00. Best seller: Classic Burger (280 units).

## 4. Unusual sales day

- **Thu Nov 5:** $476.00 vs mean of previous 4 Thursdays $977.25 → **-51.3%** (threshold ±30%) → alert at startup.
- Previous Thursdays: Oct 29 $1,026.00, Oct 22 $1,060.00, Oct 15 $954.00, Oct 08 $869.00
- Must NOT alert: Oct 14 (unknown coverage, not zero sales) and Nov 7 (partial day).

## 5. December forecast (weekday-average baseline)

- Training: 55 complete days (Sep 12 – Nov 6, Oct 14 excluded). Nov 5 included as recorded.
- December open days: 30 (closed Dec 25): Mon 4, Tue 5, Wed 5, Thu 5, Fri 3, Sat 4, Sun 4

| Dish | Mon | Tue | Wed | Thu | Fri | Sat | Sun |
|---|---|---|---|---|---|---|---|
| Classic Burger | 35.00 | 36.25 | 32.14 | 34.88 | 46.12 | 54.38 | 46.12 |
| Cheeseburger | 22.38 | 22.12 | 27.86 | 23.50 | 34.88 | 37.62 | 29.88 |
| Veggie Burger | 12.50 | 14.50 | 18.86 | 14.75 | 26.00 | 27.88 | 19.00 |

| Dish | Units (in-store / delivery) | Revenue | Low −15% | High +15% |
|---|---|---|---|---|
| Classic Burger | 1196.71 (782.66 / 414.05) | $14,360.57 | $12,206.49 | $16,514.66 |
| Cheeseburger | 831.54 (521.52 / 310.02) | $10,809.96 | $9,188.47 | $12,431.46 |
| Veggie Burger | 556.04 (367.98 / 188.05) | $6,116.39 | $5,198.93 | $7,033.85 |
| **Total** | | **$31,286.93** | $26,593.89 | $35,979.97 |

## 6. December ingredient requirement and cost

| Ingredient | Required | @ current | @ after beef increase |
|---|---|---|---|
| beef | 1014.12 lb | $4,056.50 | $4,786.67 |
| bun | 2584.29 each | $1,550.57 | $1,550.57 |
| produce | 2584.29 each | $2,584.29 | $2,584.29 |
| cheese | 831.54 each | $332.61 | $332.61 |
| veggie_patty | 556.04 each | $889.66 | $889.66 |
| **Total** | | **$9,413.63** | **$10,143.80** |

- **Price-only increase: $730.17 (+7.76%)** = 1014.12 lb beef × $0.72. Alert policy ≥5% or ≥$250 → **fires**.
- Ingredient cost / projected revenue: 30.1% → 32.4%. Excludes inventory, waste, labor, rent, delivery fees and packaging.

## 7. Backtest (synthetic data — not evidence of real-world accuracy)

Train: 41 complete days before Oct 24. Test: 14 days Oct 24 – Nov 6 (includes Nov 5).

| Method | MAE units per dish per day |
|---|---|
| Weekday average | 5.59 |
| Previous week same weekday | 6.48 |

## 8. Live demo and edge cases

Nov 7 starts with no booked receipts (in_store partial, delivery unknown).

| File | Expected result |
|---|---|
| `live_demo/1_receipt_TB-20261107-001.pdf` | Completed. Revenue +$37.00 (2 Classic, 1 Cheeseburger, in_store); total charged $39.96 |
| `live_demo/2_invoice_RF-20261107-004.pdf` | Completed. Beef $4.00 → $4.72/lb. Alerts: price increase +18.00%; December projected cost +$730.17 |
| `live_demo/3_receipt_TB-20261107-002_photo.png` | Completed (image). Revenue +$23.00 (Veggie + Classic, delivery); Nov 7 now $60.00 |
| `edge_cases/E1_duplicate_bytes_TB-20261107-001.pdf` | Duplicate (same SHA-256 and receipt number). Nothing booked twice; no new alert |
| `edge_cases/E2_conflicting_RF-20261107-004.pdf` | Needs review: same vendor + invoice number, total $104.40 vs $94.40 (freight $10.00) |
| `edge_cases/E3_pack_size_change_RF-20261107-005.pdf` | Completed. 1 × 20-lb case @ $94.40 = $4.72/lb. **No** price alert |
| `edge_cases/E4_needs_review_APC-20261107-01.pdf` | Needs review: MICROGREENS MIX (ingredient_id null) and beef case with no weight. Data-quality alert; beef price unchanged |
| `edge_cases/E4b_unknown_dish_TB-20261107-003.pdf` | Needs review: Mushroom Swiss Burger (dish_id null). Not counted in sales |
| `edge_cases/E5_late_arrival_RF-20261030-002.pdf` | Completed into history: beef $4.10/lb effective Oct 30 – Nov 2. Current price stays $4.72; no spike alert (+2.5% vs Oct 27) |

## 9. Alerts summary

Should fire: unusual sales day (Nov 5, startup); beef price increase (+18.00%); projected-cost increase (+$730.17); data-quality for E2, E4, E4b.
Must not fire: produce drift, E3 pack-size change, E5 late invoice, Oct 14 unknown day, Nov 7 partial day, E1 duplicate.

