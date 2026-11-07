# Checkpoint 5: read-only owner chat

Ask MarginGuard now interprets questions with the configured OpenRouter model, executes a validated query plan, and displays database answers, metric cards, source documents and the queries used. It supports short follow-up questions using up to six previous messages. Conversation state stays in the browser session; it is not stored in the business ledger.

## Start and test

Stop an older development server with Ctrl+C, then use the same PowerShell/database selection you used for checkpoint 4:

```powershell
cd "E:\CMU\Sophomore\Fall\NOVA Hackathon"
npm.cmd run dev
```

Open http://127.0.0.1:5173. **Ask MarginGuard** is at the bottom of **Overview**; there is no separate Ask tab. The conversation scrolls inside its panel and stays available when returning from Inbox. Existing `.env` settings are preserved. Chat requires `AI_MODE=openrouter`, `OPENROUTER_API_KEY` and a compatible `OPENROUTER_MODEL`. Keys remain server-side. Mock/unconfigured chat returns an explicit configuration error instead of simulated business answers. Restart the backend after changing `.env`.

Try these questions individually:

- What were sales in the last 7 days?
- What were delivery sales last week?
- What does the Classic Burger cost to make now?
- How has the beef price changed?
- What are next month's projected sales and ingredient costs?
- Why did next month's ingredient cost increase?
- Which alerts need my attention?

The last seven days means **today plus the six previous restaurant-local dates**, matching the live dashboard. Ask for today to see approved receipts so far, or for the last seven finished days to exclude today. Last week means the previous **Monday–Sunday calendar week**. This month/week includes the current day and reports incomplete coverage where applicable. Explicit historical as-of queries should state the date as `YYYY-MM-DD`.

Each successful answer shows its ledger version and checked time. Expand **Sources** and click an invoice/receipt source to open its document in Inbox. Expand **Queries used** to inspect exact dates, filters and tool status. Forecast-only references identify saved runs without pretending to be source PDFs.

Direct API test in another PowerShell terminal:

```powershell
$base = "http://127.0.0.1:8000"
Invoke-RestMethod "$base/api/health"

$question = @{
    question = "What were sales in the last 7 days?"
    history = @()
} | ConvertTo-Json -Depth 8

$answer = Invoke-RestMethod "$base/api/chat" -Method Post `
    -ContentType "application/json" -Body $question -TimeoutSec 45
$answer | Select-Object status, answer, source_data_version, as_of
$answer.metrics | Select-Object label, value, unit, kind, period, coverage
$answer.tools | ConvertTo-Json -Depth 8
$answer.evidence | ConvertTo-Json -Depth 8
```

Follow-up context is optional and explicitly bounded:

```powershell
$followup = @{
    question = "And for delivery?"
    history = @(
        @{ role = "user"; content = "What were sales in the last 7 days?" }
        @{ role = "assistant"; content = $answer.answer.Substring(0, [Math]::Min(2000, $answer.answer.Length)) }
    )
} | ConvertTo-Json -Depth 8
Invoke-RestMethod "$base/api/chat" -Method Post `
    -ContentType "application/json" -Body $followup -TimeoutSec 45 |
    ConvertTo-Json -Depth 10
```

## Supported tools

| Tool | Reports |
| --- | --- |
| `get_sales_summary` | Approved net item revenue, units, orders, average order revenue; optional dish/channel/day breakdowns |
| `get_ingredient_history` | First/latest normalized approved prices in a bounded period, dated invoice evidence and percent change |
| `get_dish_cost` | Effective replacement ingredient costs and optional configured channel contribution assumptions |
| `get_month_forecast` | Existing ready saved forecast, with optional dish/channel filter; no recalculation |
| `get_alerts` | Latest matching new/acknowledged/resolved alerts, with optional projected-cost horizon month |
| `explain_forecast_change` | Two compatible saved snapshots: usage/dish mix, supplier-price, interaction and cent-rounding effects |

Forecast-change analysis uses the same horizon, method, training policy, recipe versions, ingredient sets and base units. It retains the originally-ready immutable values of the older snapshot even after its live status becomes pending. Explicit older comparisons are labeled historical. Without a compatible earlier snapshot, chat says the comparison is unavailable; existing cost alerts can still supply their own measured evidence. It never invents a baseline.

For the full fictional v2 history on **November 7, 2026**:

- November 1–7 before uploading the live receipt: **264 orders, 488 units, $5,932.00** observed net sales. The live receipt adds **1 order, 3 units and $37.00** immediately after approval. The explicitly requested October 31–November 6 finished-date range remains **332 orders, 610 units, $7,400.00**.
- Before the main live invoice: beef **$4.00/lb**, Classic Burger **$3.60** replacement ingredient cost.
- After approving `2_invoice_RF-20261107-004.pdf`: beef **$4.72/lb**, Classic Burger **$3.96**.
- If ready forecasts were saved before and after that invoice: December ingredient consumption cost **$9,413.63 → $10,143.80**. Supplier-price effect **$730.17**, usage/interaction **$0.00** in that controlled example.

These are dated fixture acceptance values, not hardcoded answers. Different dates, approved receipts, recipes or coverage can change results. Loading only the small checkpoint-1 seed does not produce the full-history forecast. Use the existing checkpoint-2 import and checkpoint-4 live-demo sequence; do not reset a shared business database to reproduce an example.

## How AI and the database work together

One model request maps a question to at most four allowlisted tools. The provider sees the question, bounded conversation and a small catalog/date context. It does not receive the entire ledger. The plan must pass a strict schema and tool-specific argument validation. A second free-form model response is not used: Python calculates and renders the reported facts. This keeps numeric claims tied to approved data rather than trusting generated arithmetic.

All tools execute in one query-only SQLite snapshot, with a query time budget. No database transaction spans the provider request. Chat does not write a conversation log, mark alerts read, change prices, trigger recalculation, run arbitrary SQL or send owner messages. This checkpoint adds no database migration and preserves schema version 5.

Missing, stale or insufficient forecasts suppress current forecast totals. Unknown/partial receipt coverage remains visible. Actual profit, actual COGS, inventory on hand, platform-specific payouts and unmeasured causes of demand changes are unsupported. Delivery is the configured aggregate channel. Modeled recipe costs exclude labor, rent, waste and other operating costs.

The model still determines question routing; schema validation cannot prove perfect language understanding. Known date/channel/entity mismatches ask for clarification. Inspect the displayed query trace when a question is ambiguous, and specify the period and catalog name. Chat is intentionally a bounded reporting assistant.

## Configuration and error states

Optional settings are documented in `.env.example`; existing `.env` does not need new entries:

```dotenv
MARGINGUARD_CHAT_TIMEOUT_SECONDS=30
MARGINGUARD_CHAT_MAX_OUTPUT_TOKENS=3000
MARGINGUARD_CHAT_REASONING_EFFORT=auto
```

`auto` requests low reasoning for Gemini model names and leaves other models at their provider default. `provider` omits the reasoning parameter; explicit `minimal`, `low`, `medium` or `high` requires model support. This is separate from extraction settings. Reasoning can share the output-token budget, so a too-small budget can truncate the structured plan; see [OpenRouter's reasoning-token documentation](https://openrouter.ai/docs/guides/best-practices/reasoning-tokens). No raw provider response or reasoning is exposed in owner chat.

HTTP 503 indicates unconfigured chat or a bounded database query failure; 429 indicates another API model request is active; 502 indicates provider/auth/credits/schema failure; 504 indicates timeout. These states produce an honest error rather than a financial answer. A well-formed but unsupported or ambiguous question returns HTTP 200 with `status: unsupported` or `clarification`; missing facts return `unavailable`. Mixed tool results retain individual unavailable traces and limitations.

## Automated review

```powershell
.\.venv\Scripts\python.exe -m pytest -q
npm.cmd --prefix frontend test
npm.cmd --prefix frontend run build
.\.venv\Scripts\python.exe scripts/export_contract.py
```

The automated provider is mocked; real model smoke checks are recorded separately in [progress.md](progress.md). The exported chat example is a transparent canned query-plan fixture over seeded records, not evidence of a paid model call.
