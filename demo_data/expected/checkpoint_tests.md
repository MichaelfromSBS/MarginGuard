# Checkpoint verification with this dataset (numbers from answer_key.md)

**1. Database / contract**
- Load `config/` + `history/` into a fresh DB: 2,733 receipts and 3,655 items; 8 invoices.
- Coverage: 114 date/channel rows (56 days × 2 + Nov 7 × 2) (Oct 14 = unknown ×2; Nov 7 = partial / unknown).
- Every history receipt validates against the receipt schema.

**2. Ingestion**
- Extract the 3 `live_demo/` files and compare field-by-field with their `.expected.json`.
- E1 changes no row counts. E2, E4 and E4b go to needs_review. E3 gives $4.72/lb.
- E5 inserts a dated price (Oct 30, $4.10) without changing the current price.

**3. Metrics and forecast**
- Dish costs: Classic $3.60 → $3.96, Cheeseburger $4.00 → $4.36, Veggie $3.20.
- Oct 31 – Nov 6: 332 orders, $7,400.00 revenue.
- December (30 open days): $31,286.93 revenue; ingredient cost $9,413.63 → $10,143.80 (+$730.17).
- Oct 14 is excluded, not treated as zero.

**4. Worker and alerts**
- Current policy: see `docs/checkpoint-4.md`; the generator's `config/demo_policy.json` is historical fixture metadata, not runtime alert configuration.
- On Nov 7 startup, no historical sales alert is newly sent. The Nov 5 unusual day is reported only on Nov 6 (39 units, 24 orders, $476.00 net sales; 51.55% fewer units than the comparable-weekday mean).
- Invoice 2 creates **one combined alert**: beef $4.00 → $4.72/lb (+18%) raises projected December ingredient cost by $730.17 ($9,413.63 → $10,143.80), at unchanged demand.
- No duplicate for E3/E5 or month rollover. Partial/unknown days do not alert. Failed/held documents stay in Inbox without a business notification.

**5. Chat**
- "Sales last 7 complete days?" → $7,400.00, 332 orders.
- "Classic Burger cost now?" → $3.96.
- "Why did December cost rise?" → 1,014.12 lb × $0.72 = $730.17, citing RF-20261107-004.
