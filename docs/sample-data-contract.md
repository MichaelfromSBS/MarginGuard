# MarginGuard sample-data handoff

This contract gives the teammate generating supplier invoices and sales receipts a stable target. Checkpoint 1 defines and validates these structures; document upload, AI extraction, ingestion, forecasting and alerts are later checkpoints. The files in `examples/` are transparent synthetic source text and corresponding expected extraction JSON, not evidence that OCR or extraction has already run.

## Copyable prompt for Claude

```text
Generate fictional demo documents for MarginGuard, a restaurant finance application.
Restaurant: Tartan Burger Co. Currency: USD. Restaurant timezone: America/New_York.
Label every document FICTIONAL DEMO DATA. Include no real personal, contact,
payment-card, bank or account information. Produce readable selectable-text PDFs
for supplier invoices and clear PDFs or PNG/JPEG images for customer receipts.
Also provide UTF-8 source text and expected structured JSON for each document.

Use these canonical ingredients and base units:
beef (lb), bun (each), produce (each), cheese (each), veggie_patty (each).
Supplier Ridgeline Foodservice has vendor_id ridgeline_foodservice.
Known aliases include GROUND CHUCK 80/20 for beef, BURGER BUN for bun,
BURGER PRODUCE PORTION for produce, CHEESE SLICE for cheese, and
VEGGIE PATTY for veggie_patty. Don't silently change the grade/product under an alias.

Use exactly these dish IDs and menu prices, in both channels:
classic_burger / Classic Burger / $12.00
cheeseburger / Cheeseburger / $13.00
veggie_burger / Veggie Burger / $11.00
Channels are in_store and delivery. Print the channel on each routine receipt.

Recipes and baseline prices:
Classic Burger: 0.50 lb beef + 1 bun + 1 produce portion.
Cheeseburger: Classic Burger ingredients + 1 cheese slice.
Veggie Burger: 1 veggie_patty + 1 bun + 1 produce portion.
Initial prices: beef $4.00/lb, bun $0.60/each, produce $1.00/each,
cheese $0.40/each, veggie_patty $1.60/each.

Main new invoice dated 2026-11-07:
RF-20261107-004, Ridgeline Foodservice, 2 cases of beef, 10 lb per case,
$47.20 per case, line/subtotal/total $94.40, tax and freight $0.00.
This is $4.72/lb, exactly 18% higher than $4.00/lb.
Earlier baseline invoice beef can be 2 x 10-lb cases at $40.00/case,
line total $80.00. Use distinct invoice numbers and earlier dates.

Main sample receipt:
TB-20261107-001 at 2026-11-07T12:30:00-05:00, channel in_store, completed.
2 Classic Burgers at $12.00 = $24.00; 1 Cheeseburger at $13.00 = $13.00.
Subtotal $37.00; discount $0.00; illustrative tax $2.96; tip $0.00;
total $39.96. This tax is fictional, not a jurisdictional tax claim.

Routine receipts must reconcile exactly and have unique IDs. Keep routine
fixtures completed, with no discounts or refunds. If eight weeks of historical
receipts are generated, provide an index by local date and channel specifying
complete, partial, unknown or closed coverage. Do not imply zero sales merely
because a date has no receipt file. Use variable but plausible daily quantities.
Do not hard-code a forecast output: later forecast code must derive it.

For expected JSON, represent money, quantities, pack sizes and unit prices as
decimal STRINGS, never JSON numeric floats. Use USD. Dates use YYYY-MM-DD;
sale timestamps include an explicit correct UTC offset for America/New_York.
For dates before the 2026-11-01 daylight-saving transition, use the correct
-04:00 offset; timestamps after the transition use -05:00. Avoid ambiguous
transition-hour timestamps in demo fixtures.

Invoice JSON fields:
vendor_id (nullable), vendor_name, invoice_number, invoice_date, currency,
subtotal, tax, freight, total, items[].
Each invoice item: description, ingredient_id (nullable), quantity,
purchase_unit (lb/oz/each/case), pack_size (nullable decimal string),
pack_unit (nullable lb/oz/each), unit_price, line_total, source_page (integer),
source_text (exact source substring).

Receipt JSON fields:
receipt_number, sold_at, channel_id (nullable), status
(completed/void/refund), currency, subtotal, discount, tax, tip, total, items[].
Each receipt item: description, dish_id (nullable), quantity, unit_price,
gross_amount, discount_amount, net_amount, source_page (integer),
source_text (exact source substring).

Use null, never an invented ID, if a document intentionally omits its channel
or contains an unknown ingredient/dish. Include explicit null pack fields when
no packaging conversion is applicable. source_page starts at 1.

Keep edge-case documents separate from routine demo records:
1. Exact duplicate bytes of a receipt, to test idempotency.
2. Same vendor/invoice number with a different total, to test review handling.
3. After beef is $4.72/lb, a case-size change: 1 x 20-lb case at $94.40.
   The price per case doubles but the price per pound is unchanged.
4. An unknown item or omitted case weight, expecting Needs review.
5. An older invoice arriving after a newer one, to test effective-date history.
6. A partial day's receipt batch, explicitly marked partial.

Supply a manifest listing each file, document type, business ID, expected state,
and expected financial amounts. Never mix negative-control or malformed files
into historical complete-day totals. All expected source_text values must be
literal passages from that document's text. Use the exact field names above;
do not add an alternative envelope around the extraction JSON.
```

## Canonical identifiers and unit conventions

| Entity | ID | Meaning |
| --- | --- | --- |
| Ingredient | `beef` | Ground beef, base unit lb |
| Ingredient | `bun` | One burger bun, base unit each |
| Ingredient | `produce` | One prepared produce portion, base unit each |
| Ingredient | `cheese` | One cheese slice, base unit each |
| Ingredient | `veggie_patty` | One veggie patty, base unit each |
| Dish | `classic_burger` | Classic Burger |
| Dish | `cheeseburger` | Cheeseburger |
| Dish | `veggie_burger` | Veggie Burger |
| Channel | `in_store` | In-store sale |
| Channel | `delivery` | Delivery sale; does not identify a particular platform |

Use `null` for unresolved mappings, not `"unknown"` or a made-up catalog ID. Source timestamps carry an offset; period grouping uses restaurant-local dates. Weight and count are different dimensions: do not convert each to lb without a known recipe-specific conversion.

For a case item, `quantity` counts cases, `unit_price` is the price per case, and `pack_size`/`pack_unit` describe each case's contents. For direct purchases in lb, oz or each, pack fields can be null. Financial documents retain their purchase units; normalization to the ingredient base unit is a calculation performed later.

## Extraction field contract

All fields below belong to the extraction object. Monetary/quantity values are JSON strings such as `"47.20"` and `"0.50"`. No thousands separators, currency symbols or scientific notation are needed in those strings. Display-format currency symbols remain in the original document text.

Invoice header:

| Field | Type / rule |
| --- | --- |
| `vendor_id` | String or null; known catalog/vendor suggestion |
| `vendor_name` | Nonempty source supplier name |
| `invoice_number` | Source business identifier, not a filename |
| `invoice_date` | ISO local date |
| `currency` | `USD` for this MVP |
| `subtotal`, `tax`, `freight`, `total` | Decimal strings |
| `items` | Nonempty array of invoice items |

Each invoice item contains `description`, nullable `ingredient_id`, decimal-string `quantity`, `purchase_unit`, nullable decimal-string `pack_size`, nullable `pack_unit`, decimal-string `unit_price` and `line_total`, integer `source_page`, and literal `source_text`.

Receipt header:

| Field | Type / rule |
| --- | --- |
| `receipt_number` | Source receipt/order identifier |
| `sold_at` | ISO timestamp with explicit UTC offset |
| `channel_id` | `in_store`, `delivery`, or null |
| `status` | `completed`, `void`, or `refund`; routine demo inputs are completed |
| `currency` | `USD` for this MVP |
| `subtotal`, `discount`, `tax`, `tip`, `total` | Decimal strings |
| `items` | Nonempty array of receipt items |

Each receipt item contains `description`, nullable `dish_id`, decimal-string `quantity`, `unit_price`, `gross_amount`, `discount_amount`, `net_amount`, integer `source_page`, and literal `source_text`.

Schema-valid does not mean financially approved. A later ingestion checkpoint will apply catalog, arithmetic, document-status and duplicate checks. In particular, schema support for `refund` or `void` is not a promise that those documents will be automatically booked as ordinary sales.

## Reconciliation and known answers

- Invoice: `2 × 47.20 = 94.40`; `2 × 10 = 20 lb`; `94.40 / 20 = 4.72/lb`.
- Invoice total: `subtotal + tax + freight = total` for the no-credit fixtures.
- Receipt: `2 × 12 + 1 × 13 = 37.00`; `37.00 - 0.00 + 2.96 + 0.00 = 39.96`.
- Receipt item: `gross_amount - discount_amount = net_amount`; item nets sum to subtotal minus header discount.
- Receipt revenue for the sample is $37.00, not the $39.96 charged total: tax and tips are separate.
- Current Classic Burger ingredient cost is `0.50 × 4.72 + 0.60 + 1.00 = 3.96`.
- The pack-size negative control remains $4.72/lb and must not become a price-spike event.

The files [invoice.txt](../examples/invoice.txt), [invoice.expected.json](../examples/invoice.expected.json), [receipt.txt](../examples/receipt.txt), and [receipt.expected.json](../examples/receipt.expected.json) are the canonical paired examples. Their expected JSON is intended for later extraction tests. It is not an upload endpoint payload in checkpoint 1.

## History and coverage handoff

Forecasts require chronological sales history with coverage evidence. Provide a separate coverage index keyed by `date` and `channel_id`, with `status` equal to `complete`, `partial`, `unknown`, or `closed`. A complete-day declaration means the fixture set includes all receipts for that day/channel, including an explicit zero-sales day when applicable. Closed means not trading, not missing data. Do not mark all historical days complete merely because some receipts exist.

Keep forecasting-training history separate from live-demo documents and negative controls. Include earlier baseline supplier prices before the live price-change invoice. Do not count the same receipt in both a summary import and a later document import. Eight-week historical fixture ingestion and forecasting are not implemented in checkpoint 1.
