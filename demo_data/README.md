# MarginGuard demo data (v2, matches `docs/sample-data-contract.md`)

All data is **FICTIONAL DEMO DATA**: Tartan Burger Co. (USD, America/New_York), Ridgeline Foodservice (`ridgeline_foodservice`) and Allegheny Produce Co. (no vendor_id). Prepared for NOVA 2026; disclose it as prepared fixture data.

Catalog, IDs, prices, recipes, field names, decimal strings, timestamp offsets and statuses follow the contract exactly. Illustrative tax is 8%, rounded half-up per receipt (not a jurisdictional tax claim).

## Layout
| Path | Contents |
|---|---|
| `config/` | ingredients (with aliases), dishes, menu_prices, recipes, channels (fee/packaging = checkpoint-1 seed values), vendors, calendar (closed Nov 26, Dec 25), demo_policy.json |
| `history/receipts.jsonl` | 2,733 completed receipts Sep 12 – Nov 6. **One contract receipt-extraction object per line.** No discounts/voids/refunds |
| `history/receipt_sources.jsonl` | `{receipt_number, source_text}`: the literal receipt text each record's `source_text` values come from |
| `history/coverage.csv` | `date, channel_id, status` (complete / partial / unknown). Oct 14 unknown in both channels; Nov 7 in_store partial, delivery unknown |
| `history/invoices/` | 8 weekly Ridgeline invoices (Sep 15 – Nov 3): `.pdf` + literal `.txt` + `.expected.json` |
| `live_demo/` | The three demo documents (PDF / PNG + `.txt` + `.expected.json`) |
| `edge_cases/` | The contract's negative controls, kept separate from history |
| `manifest.csv` | Every document: type, business ID, category, expected state, expected amounts |
| `expected/` | `answer_key.md`, `expected_metrics.json`, `checkpoint_tests.md` |

## Live demo (in order)
1. `1_receipt_TB-20261107-001.pdf`: the contract's main sample receipt (2 Classic + 1 Cheeseburger, $37.00 revenue, $39.96 total).
2. `2_invoice_RF-20261107-004.pdf`: the contract's main invoice (2 × 10-lb cases @ $47.20, so beef $4.72/lb, +18%).
3. `3_receipt_TB-20261107-002_photo.png`: image input (Veggie + Classic, delivery, $23.00).

## Edge cases
E1 exact duplicate bytes · E2 same invoice number with a different total · E3 20-lb case at the same $/lb · E4 unknown item + omitted case weight · E4b unknown dish · E5 older invoice arriving late · partial day = Nov 7 coverage rows.

## Loading notes
- `history/` is a bulk import into a **fresh** database. It replaces, and must not be mixed with, the checkpoint-1 built-in seed (`DEMO-1001`, `DEMO-R001` …), which would duplicate Nov 6–7 sales.
- Load the 8 history invoices from their `.expected.json` (no AI calls needed), or run the PDFs through extraction as a test.
- Every `.expected.json` reconciles arithmetically, and every `source_text` appears literally in its `.txt` and in the PDF's extracted text (verified).
