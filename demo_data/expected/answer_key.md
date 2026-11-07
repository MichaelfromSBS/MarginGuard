# MarginGuard — expected results (answer key)

Everything here is computed from the files in `config/` and `seed/` plus the live documents. All data is fictional.
Revenue = net item revenue (items − discounts) of **completed** receipts; excludes tax, tips, voided and refunded receipts.

## 1. Ingredient prices (normalized to base unit)

| Ingredient | Unit | Price history (invoice date: $/unit) | Current (before live demo) | After INV-30440 |
|---|---|---|---|---|
| beef | lb | 09-15: 4; 09-22: 4; 09-29: 4; 10-06: 4; 10-13: 4; 10-20: 4; 10-27: 4; 11-03: 4 | $4.0000 | $4.7200 |
| chicken | lb | 09-15: 3; 09-22: 3; 09-29: 3; 10-06: 3; 10-13: 3; 10-20: 3; 10-27: 3; 11-03: 3 | $3.0000 | $3.0000 |
| bun | each | 09-15: 0.5; 09-22: 0.5; 09-29: 0.5; 10-06: 0.5; 10-13: 0.5; 10-20: 0.5; 10-27: 0.5; 11-03: 0.5 | $0.5000 | $0.5000 |
| cheddar | slice | 09-15: 0.2; 09-22: 0.2; 09-29: 0.2; 10-06: 0.2; 10-13: 0.2; 10-20: 0.2; 10-27: 0.2; 11-03: 0.2 | $0.2000 | $0.2000 |
| lettuce | lb | 09-15: 2.4; 09-22: 2.4; 09-29: 2.4; 10-06: 2.4; 10-13: 2.4; 10-20: 2.4; 10-27: 2.4; 11-03: 2.4 | $2.4000 | $2.4000 |
| tomato | lb | 09-15: 2; 09-22: 2; 09-29: 2.1; 10-06: 2.1; 10-13: 2.05; 10-20: 2; 10-27: 2; 11-03: 2 | $2.0000 | $2.0000 |
| fries | lb | 09-15: 2; 09-22: 2; 09-29: 2; 10-06: 2; 10-13: 2; 10-20: 2; 10-27: 2; 11-03: 2 | $2.0000 | $2.0000 |
| fryer_oil | lb | 09-15: 1.286; 09-22: 1.286; 09-29: 1.286; 10-06: 1.286; 10-13: 1.286; 10-20: 1.286; 10-27: 1.286; 11-03: 1.286 | $1.2857 | $1.2857 |
| takeout_bag | each | 09-15: 0.06; 09-22: 0.06; 09-29: 0.06; 10-06: 0.06; 10-13: 0.06; 10-20: 0.06; 10-27: 0.06; 11-03: 0.06 | $0.0600 | $0.0600 |

- **Package-size trap:** INV-30407 (Oct 27) sells beef as a 20 LB CASE at $80.00 → still **$4.00/lb**. This must NOT be flagged as a price increase.
- Tomato moves $2.00 → $2.10 → $2.05 → $2.00 (≤ 5%): below the 10% threshold, so no alert.
- **Beef: $4.00 → $4.72/lb (+18.0%)** on INV-30440 (2 cases × 10 lb at $47.20) → ingredient price-increase alert.

## 2. Dish ingredient cost

| Dish | Price | Cost before | Cost after | Ingredient cost % before → after |
|---|---|---|---|---|
| Classic Burger | $12.00 | $3.60 | $3.96 | 30.0% → 33.0% |
| Crispy Chicken Sandwich | $11.00 | $2.60 | $2.60 | 23.6% → 23.6% |
| Side of Fries | $4.50 | $0.80 | $0.80 | 17.8% → 17.8% |

Classic Burger matches the spec's example: beef $2.00 → $2.36 per burger; other ingredients $1.60; total $3.60 → $3.96.

## 3. Sales history (Sep 12 – Nov 7)

Coverage: complete every day except **Oct 14 (missing import)** and **Nov 7 (partial — trading in progress, imported to 11:30)**.

| Week (Sun–Sat) | Complete days | Orders | Net revenue | Classic Burger | Chicken Sandwich | Side of Fries |
|---|---|---|---|---|---|---|
| Sep 06 | 1/1 | 60 | $1,030.50 | 42 | 38 | 25 |
| Sep 13 | 7/7 | 346 | $6,178.00 | 289 | 196 | 128 |
| Sep 20 | 7/7 | 328 | $5,829.00 | 270 | 183 | 136 |
| Sep 27 | 7/7 | 353 | $6,475.00 | 295 | 220 | 122 |
| Oct 04 | 7/7 | 348 | $6,162.00 | 268 | 219 | 126 |
| Oct 11 | 6/7 | 311 | $5,728.50 | 260 | 193 | 115 |
| Oct 18 | 7/7 | 339 | $6,262.00 | 303 | 194 | 116 |
| Oct 25 | 7/7 | 362 | $6,577.00 | 308 | 210 | 134 |
| Nov 01 | 6/7 | 254 | $4,697.00 | 199 | 161 | 124 |

"Last 7 complete days" (Oct 31 – Nov 6): 321 orders, $5,925.00 net revenue, avg $18.46/order. Best seller: Classic Burger (256 units).

Channel split, same period: in-store $3,665.50 · delivery $2,259.50.

History contains 2752 receipts: 28 voided and 23 refunded (both excluded from revenue).

## 4. Unusual sales day (should alert at startup)

- **Thu Nov 5:** net revenue $378.00 vs mean of previous 4 Thursdays $861.38 → **-56.1%** (threshold ±30%).
- Previous Thursdays: Oct 29 $968.00, Oct 22 $816.00, Oct 15 $773.00, Oct 08 $888.50
- **Nov 7 must NOT alert:** partial day ($88.50 so far from 4 receipts).
- **Oct 14 must NOT alert or count as zero:** missing import, excluded from baselines and forecasts.

## 5. December forecast (weekday-average baseline)

- History: 55 complete days, Sep 12 – Nov 6 (Oct 14 excluded; Nov 7 partial excluded). Nov 5 is included as recorded.
- December open days: 30 (closed Dec 25). Weekday counts: Mon 4, Tue 5, Wed 5, Thu 5, Fri 3, Sat 4, Sun 4

Weekday averages (units/day, both channels):

| Dish | Mon | Tue | Wed | Thu | Fri | Sat | Sun |
|---|---|---|---|---|---|---|---|
| Classic Burger | 30.1 | 35.0 | 33.9 | 38.2 | 48.4 | 52.2 | 44.8 |
| Crispy Chicken Sandwich | 22.1 | 21.9 | 26.7 | 24.2 | 37.5 | 39.5 | 33.1 |
| Side of Fries | 15.2 | 15.2 | 18.3 | 16.4 | 21.8 | 22.8 | 20.8 |

| Dish | Projected units (in-store / delivery) | Projected revenue | Low (−15%) | High (+15%) |
|---|---|---|---|---|
| Classic Burger | 1,189.2 (806.8 / 382.4) | $14,269.93 | $12,129.44 | $16,410.42 |
| Crispy Chicken Sandwich | 855.7 (555.3 / 300.4) | $9,412.66 | $8,000.76 | $10,824.56 |
| Side of Fries | 549.8 (381.5 / 168.3) | $2,474.12 | $2,103.00 | $2,845.23 |
| **Total** | | **$26,156.71** | $22,233.20 | $30,080.21 |

## 6. December ingredient requirement and cost

| Ingredient | Required | Cost @ current | Cost @ after INV-30440 |
|---|---|---|---|
| beef | 594.6 lb | $2,378.32 | $2,806.42 |
| bun | 2,044.9 each | $1,022.43 | $1,022.43 |
| cheddar | 1,189.2 slice | $237.83 | $237.83 |
| lettuce | 102.2 lb | $245.38 | $245.38 |
| tomato | 184.0 lb | $368.07 | $368.07 |
| fries | 833.4 lb | $1,666.76 | $1,666.76 |
| chicken | 342.3 lb | $1,026.84 | $1,026.84 |
| **Total** | | **$6,945.63** | **$7,373.73** |

- **Price-only increase: $428.10 (+6.2%)** at unchanged projected demand — all from beef (594.6 lb × $0.72).
- Projected-cost alert policy: ≥5% or ≥$250 → **alert fires** ($428.10).
- Projected ingredient cost as % of projected revenue: 26.6% → 28.2%.
- Excludes inventory on hand, waste, purchasing schedules, labor, rent and other expenses.

## 7. Backtest (synthetic data — not proof of real-world accuracy)

Train: complete days before Oct 24 (41 days). Test: Oct 24 – Nov 6 (14 days, includes the unusual Nov 5).

| Method | MAE units/dish/day | MAE daily revenue* |
|---|---|---|
| Weekday average | 5.84 | $95.36 |
| Previous week same weekday | 7.05 | $123.14 |

*Weekday-average revenue = projected units × list price (ignores discounts); naive revenue = actual net revenue of the same weekday last week.

## 8. Live demo documents — expected effect

Nov 7 before the demo: 4 completed receipts, $88.50 net revenue (partial day).

- **1_receipt_R-20261107-0006.pdf** → approved. +$28.50 net revenue (2× Classic Burger, 1× Side of Fries; in_store). Nov 7 now 5 orders, $117.00.
- **2_invoice_INV-30440_beef_increase.pdf** → approved. Beef $4.00 → $4.72/lb. Alerts: ingredient price increase (+18.0%) and projected-cost increase (+$428.10 for December).
- **3_receipt_R-20261107-0007_photo.png** → approved. +$21.00 net revenue (1× Crispy Chicken Sandwich, 1× Classic Burger; delivery). Nov 7 now 6 orders, $138.00.
- **4_receipt_R-20261107-0006_REIMPORT.pdf** → recognized as duplicate of receipt 1 (same receipt_id). Revenue stays $138.00; no new alert.
- **5_invoice_APC-7781_needs_review.pdf** → **Needs review** (3 issues: Roma tomatoes missing case weight; 'MICROGREENS MIX' not in catalog; lettuce line 3 × $12.00 = $36.00 but printed $39.00). Data-quality alert. Tomato and lettuce prices unchanged.
- **6_receipt_R-20261107-0008_unknown_item.pdf** → **Needs review** (unknown dish 'Mushroom Swiss Burger', $13.50). Not counted in sales until resolved. Revenue stays $138.00.

## 9. Alerts the demo should show

| # | When | Type | Finding |
|---|---|---|---|
| 1 | Startup | Unusual sales day | Thu Nov 5 -56.1% vs previous 4 Thursdays |
| 2 | Invoice 2 | Ingredient price increase | Beef +18.0% ($4.00 → $4.72/lb), INV-30440 |
| 3 | Invoice 2 | Projected-cost increase | December ingredient cost +$428.10 (+6.2%) |
| 4 | Invoice 5 | Data-quality exception | APC-7781: 3 lines need review |
| 5 | Receipt 6 | Data-quality exception | R-20261107-0008: unknown dish |

Must **not** alert: Oct 27 beef 20 lb case (same $/lb), tomato drift, Oct 14 missing day, Nov 7 partial day, receipt 4 re-import.

