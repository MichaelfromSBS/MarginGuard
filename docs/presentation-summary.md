# MarginGuard — presentation notes

Prepared at hackathon close. See the [project README](../README.md) for current models, interface behavior, visitor setup and the People's Choice Top 5 result.

## One-line pitch

MarginGuard turns restaurant invoices and sales receipts into live financial visibility, next-month planning, and alerts that explain what changed and why it matters.

## Problem–solution summary

Restaurant owners receive supplier invoices and customer receipts as separate records. An invoice can reveal a higher ingredient price, but understanding its consequences requires connecting purchasing units, dish recipes and expected sales. Receipts show what sold, but the owner still needs an up-to-date picture of revenue and demand.

MarginGuard connects those records into one ongoing workflow. AI reads PDFs and photos; validation checks the extracted fields; approved records update a persistent database. Python then calculates observed sales, ingredient prices, replacement ingredient costs per dish, and next month's projected sales and ingredient consumption. The system monitors for ingredient-driven increases in projected costs and unusually low completed-day sales. The owner can inspect the evidence or ask questions and follow-ups in natural language.

The business value is earlier visibility into which dishes are becoming more expensive, how much a supplier change affects planning, and which sales days deserve investigation. Owners can use that information when reviewing suppliers, menu pricing and purchasing plans.

## Short spoken pitch

“A restaurant's supplier invoice might say beef got more expensive. But the owner needs to know which dishes it affects and what it means for next month's ingredient costs. MarginGuard makes that connection automatically. It reads invoices and receipts, updates the restaurant's records, calculates dish costs and forecasts, and raises an alert with the source evidence. Owners can then ask what changed, or simply ask, ‘What does that mean?’ AI reads and explains; Python does the math.”

## What the finished prototype does

- Accepts supplier invoice and customer receipt PDFs or photos through Inbox; the worker can also watch a local folder.
- Extracts structured fields with AI, validates arithmetic and catalog mappings, and holds questionable documents for review.
- Updates current observed sales, order counts, dish quantities and effective supplier prices after approval. The website refreshes live sales every three seconds.
- Connects normalized ingredient prices to configured recipes and models each dish's replacement ingredient cost.
- Projects next calendar month's sales and ingredient consumption from complete historical days, with low/base/high demand scenarios.
- Creates website-only alerts for combined ingredient/projected-cost increases and yesterday's unusually low sales when coverage is complete.
- Answers financial questions through read-only database tools and offers separately labeled qualitative explanations and follow-ups.
- Lets owners acknowledge and resolve alerts and open the original source records.

## Tech summary

| Layer | Implementation | Purpose |
| --- | --- | --- |
| Interface | React, TypeScript, Vite | Overview, Trends & Outlook, Inbox, floating chat and in-app alerts |
| API | Python, FastAPI, Pydantic | Typed contracts, validation and read/write workflows |
| AI access | OpenRouter over asynchronous HTTP; Gemini and GPT-4o tested | Document interpretation, question planning, explanations and optional alert suggestions |
| Data | SQLite | Approved documents, receipt items, normalized supplier prices, recipes, coverage, forecasts and alert state |
| Background processing | Independent Python worker with persistent jobs, retries and leases | Processing and monitoring continue independently of a dashboard request |
| Analytics | Python Decimal and explicit business rules | Exact monetary calculations, unit conversions, recipe costs and anomaly evidence |
| Forecasting | Weekday averages by dish/channel, versioned snapshots, holdout evaluation | A transparent statistical planning baseline using complete historical days |

Architecture:

Documents → AI extraction → validation/review → approved database records → calculations and saved forecasts → alerts, dashboard and owner chat.

An independent worker runs the processing and monitoring loop. The frontend reads the same database through the API. Chat plans select from six allowlisted tools: sales, ingredient history, dish costs, saved forecasts, alerts, and forecast-change comparisons.

## Strongest numerical example

Use the fictional Tartan Burger Co. demo. With projected demand held constant, approving the prepared beef-price invoice produces:

| Measure | Before | After |
| --- | --- | --- |
| Ground beef supplier cost | $4.00/lb | $4.72/lb |
| Classic Burger replacement ingredient cost | $3.60 | $3.96 |
| December projected ingredient consumption cost | $9,413.63 | $10,143.80 |

That is an **18% beef-price increase** and a **$730.17 increase in projected monthly ingredient cost** in this controlled example. The alert names the ingredient responsible and links the supporting invoice evidence.

A separate prepared receipt adds **$37.00 in net food sales, one order and three dishes** after approval. Its total customer payment is $39.96, including tax; the sales metric correctly excludes the tax. Current-day totals remain labeled partial.

These are fixture-based planning results. The monthly difference is an additional projected cost, not demonstrated savings or actual profit lost.

## Interesting details worth highlighting

1. **One document has consequences across the product.** A new supplier price flows through ingredient normalization, recipes, dish costs, monthly projections and an owner alert. A new receipt flows into current sales and order statistics.

2. **AI reads and explains; Python does the math.** Extraction and language understanding use the model. Money, units, anomaly findings and forecast arithmetic are calculated in code. Financial chat answers use validated tools; conceptual explanations are labeled separately.

3. **The package-size trap.** A more expensive case is not necessarily a more expensive ingredient. The demo invoice is two ten-pound cases at $47.20 per case, which normalizes to $4.72 per pound. Repacking at the same normalized price does not create a false price increase.

4. **Immediate visibility without partial-day bias.** Today's approved receipts appear immediately in observed sales. Forecast training and unusual-sales checks use finished, complete days, so an unfinished lunch shift is not treated as a full day of weak demand.

5. **A missing day is not a zero-sales day.** Coverage distinguishes complete, partial, unknown and closed dates. Missing receipts are not silently converted into a demand collapse.

6. **Cost changes can be explained mathematically.** Compatible saved forecasts separate ingredient usage/dish-mix changes, supplier-price changes, their interaction and cent-rounding effects. The supplier demo isolates the price effect by holding demand fixed.

7. **Repeat uploads do not become repeat business.** File hashes and invoice/receipt business identifiers protect the ledger from double counting. Repeated worker scans do not repeatedly announce the same supplier change.

8. **Evidence and history stay available.** Source references, original documents and versioned forecast snapshots help the owner inspect a result and understand a before/after change.

9. **Engineering beyond the happy path.** The latest backend verification passed 373 tests; the frontend passed seven automated tests plus production builds and desktop/mobile browser checks. Live model checks covered document extraction and conversational follow-ups.

For a short presentation, prioritize the first four points; retain the others for technical questions.

## Suggested three-minute presentation

- **0:00–0:25 — Problem:** introduce the owner and the gap between scattered paperwork and a useful operating decision.
- **0:25–0:45 — Baseline:** show current sales, Classic Burger ingredient cost and the saved next-month outlook.
- **0:45–1:35 — Main moment:** upload the new supplier invoice. Show the beef-price change, updated dish cost, combined cost alert and monthly impact. Open its evidence.
- **1:35–2:00 — Receipts:** upload the customer receipt and show the additional $37.00, one order and three dishes after approval.
- **2:00–2:35 — Conversation:** ask about the burger's ingredient cost, then “What does that mean?” or “Is that my profit?” Show the difference between a sourced financial answer and an explanation.
- **2:35–3:00 — Technical takeaway and close:** explain the worker/database architecture and the division between AI interpretation and exact calculations.

Allow processing time in the live flow: an upload changes metrics after extraction and approval, not immediately upon file acceptance. Rehearse on a fresh, separate demo database so the prepared documents have not already been counted. The supplier-price alert is the strongest current live alert moment. The unusual-sales policy reports only yesterday; older historical anomalies should be shown with their actual report dates if included.

## Accurate scope for presentation questions

- The demo restaurant and historical data are fictional: eight historical supplier invoices and 2,733 receipts, with separate live documents. Imported history is prepared fixture data; live extraction is a separate demonstrated capability.
- The forecast is an interpretable weekday statistical baseline, not a newly trained neural model. Low/high scenarios vary demand; they are not calibrated confidence intervals. Synthetic holdout results do not establish real-world accuracy.
- Ingredient consumption projections and replacement recipe costs are planning measures. Full profit, actual COGS, stock levels and purchase quantities require additional inputs.
- Current inputs are uploaded files and a local watched folder. POS APIs and forwarded-email ingestion are future integrations. Alerts stay inside the website.
- Preserve the pre-event preparation disclosure in PREEXISTING.md when describing what was built during the hackathon.

Closing line: “MarginGuard connects each new restaurant document to the costs, sales and decisions it affects.”
