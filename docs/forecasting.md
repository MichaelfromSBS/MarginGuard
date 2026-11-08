# Forecasting and ingredient-price planning

## Use in the app

1. Install `.venv/Scripts/python.exe -m pip install -r requirements-forecasting.lock.txt` for optional ML models. Restart the API and worker after upgrading.
2. Open **Trends & Outlook**. Choose a demand model; the forecast updates automatically.
3. Inspect its seven-day holdout MAE against the weekday and previous-week baselines on the same complete observations. A short fictional history does not demonstrate real-world accuracy.
4. Under **Ingredient prices → menu prices → demand**, keep latest approved supplier prices or choose one ingredient and enter an optional future price per its normalized base unit.
5. Choose the percentage of the ingredient cost change to pass to customers, a price-elasticity assumption and optionally a cost comparison date. The scenario updates automatically after a short pause in typing.
6. Inspect the animated daily curve and proposed dish prices, demand, revenue and consumption cost. Switch between dishes sold, revenue and ingredient cost. The gray line is the current-menu forecast; the blue line is the pricing scenario. Expand scenario details for ingredient requirements, price provenance and limits.

The curve draws in about 650ms on tab entry and when its data changes; reduced-motion preferences disable this animation. Pricing inputs calculate after a 350ms typing pause, canceling obsolete requests and discarding late responses. Invalid inputs pause calculation and show a correction message. Model selections calculate immediately, and missing/stale forecasts are refreshed automatically. Pricing inputs are retained across model switches. Chart values are daily display allocations of the same per-series model and scenario results; backend monthly Decimal totals remain authoritative.

The comparison date defaults to 28 days before the forecast as-of date. This captures changes already present in newly approved invoices, as well as optional future price assumptions. All ingredient changes since the reference date are included. To isolate an optional future price change, use the forecast as-of date as the comparison date.

## Adaptive model selection

Choose **Auto · adaptive ensemble** to let the forecaster select a model mix. Auto is the default for new installations and older saved preferences. The upgrade happens once; later explicit model choices remain selected across refreshes and restarts. There are five candidates: weekday average, seasonal naive, recency-weighted weekday average (14-day half-life), regularized Poisson regression and Poisson gradient boosting.

The selector runs at up to four past weekly origins, 28/21/14/7 days before the prediction origin. Each training window precedes its validation dates, and every validation target precedes the actual forecast origin. Weights are separate for each dish/channel and lead bucket (1–7, 8–14 and 15–28 days). Candidates need predictions for at least 90% of eligible validation cases; errors then use their exact common cases. At least fourteen scored cases across two origins are required. Otherwise the weekday baseline is used.

A candidate must improve validation MAE over the baseline by more than 3% before weights change. A clear winner can receive most non-baseline weight; otherwise up to three competitive models are blended with inverse-squared `(1 + MAE)` weights. The choice is shrunk toward the baseline, retaining at least 25% baseline weight; small samples retain more. Beyond 28 days, the longest validated bucket is used while model deviations decay toward baseline by `28 / lead`. This is a stability rule for longer extrapolation, not evidence of accuracy beyond the validated leads.

The seven-day holdout evaluates the entire selector fitted strictly before that holdout, rather than reusing weights chosen after seeing its outcomes. Validation windows overlap, so their errors are dependent and selection scores are not unbiased accuracy estimates. No real-world accuracy gain is claimed from this short fictional corpus. Missing optional models are excluded and recorded; statistical candidates remain usable without scikit-learn.

The unchanged fictional corpus's final-week holdout scored 42 dish/channel/day cases: adaptive MAE 4.64084882, weekday MAE 4.64739229 and prior-week MAE 5.40476190. This is a small exploratory difference, not evidence of significant or real-world accuracy. The actual forecast made ten blend and eight baseline decisions. The [saved report](../examples/forecasting/adaptive-demo.json) includes full metadata.

Saved metadata records candidate availability, validation origins, scored cases, MAE, weights and selection reasons. Expand **Adaptive model mix** to inspect the choices. Source-code implementation version 4 distinguishes optimized snapshots from previous serving versions. The chronological evaluation principle follows [TimeSeriesSplit's guidance](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html).

## Chart interaction

The forecast uses monotone cubic interpolation through the daily values, preserving peaks and zeros rather than overshooting them. Smoothing changes presentation only. The displayed model is named beside the date range. Chart scales stay consistent while comparing models on the same records/month, so changes in magnitude remain visible. Hover above a day to see a faint guide that slides between dates over 160ms. Two compact, nearly transparent cards above the plot show current-menu and scenario values for the selected chart measure. Their position leaves the entire curve unobstructed. Reduced-motion settings disable the slide. Keyboard users can focus the chart and use arrows, Home, End and Escape. Touch/pointer input is supported. The approach uses the same shape-preserving principle described in the [PCHIP documentation](https://docs.scipy.org/doc/scipy/reference/generated/scipy.interpolate.PchipInterpolator.html), implemented directly in the frontend with no new chart dependency.

## Two explicit layers

The demand layer offers the unchanged weekday average, regularized Poisson regression and histogram gradient boosting with Poisson loss. Fitted candidates use dish/channel, calendar features, past unit lags and rolling statistics. Training uses complete finished local days; unknown/partial days are excluded rather than converted to zero. Known closures yield zero forecasts. Predictions bridge the remaining current-month dates recursively before the next-calendar-month horizon, using previous predictions as future lags.

Model and benchmark share `demand_models.py`. Poisson regression uses one-hot encoding, imputation, scaling and L2 regularization. Boosting uses a fixed random seed and disables random validation splitting. Preprocessing never fits on held-out targets. Existing approved quantities are retained; no new historical data is generated. See the official [PoissonRegressor documentation](https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.PoissonRegressor.html) and [time-series lag evaluation example](https://scikit-learn.org/stable/auto_examples/applications/plot_time_series_lagged_features.html).

Each saved forecast records its method, source version, training cutoff, prediction origin, implementation version and (for ML) scikit-learn version. New data/date/policy refits demand; repeated identical requests reuse immutable predictions. The last successful saved policy is reused by the worker, including after restart. Selection is stored in the existing worker-state table, separately from immutable forecast-run creation timestamps; no schema migration is needed. Models are explicit experimental choices, with no automatic promotion or silent method substitution. Missing dependencies return HTTP 503 with install instructions; choose the weekday method to continue without scientific packages.

The ordinary forecast prices recipes at current approved supplier prices and revenue at current menu prices. It assumes current demand patterns continue and does not estimate a causal menu-price response. The separate pricing layer answers what changes *if* the owner reprices:

```
recipe_cost = sum(recipe_quantity × supplier_price)
proposed_menu_price = current_menu_price
                    + (pass_through_pct / 100) × (scenario_recipe_cost − reference_recipe_cost)
scenario_units = baseline_units × (proposed_menu_price / current_menu_price) ^ elasticity
scenario_revenue = scenario_units × proposed_menu_price
scenario_ingredient_quantity = sum(scenario_units × recipe_quantity)
scenario_ingredient_cost = sum(scenario_ingredient_quantity × scenario_supplier_price)
```

Menu prices round to cents before demand is computed. Financial arithmetic uses Decimal, including the elasticity calculation; row allocations reconcile to totals. 100% pass-through preserves the dollar amount of ingredient cost change, rather than transferring the ingredient percentage increase directly. At 0%, ingredient costs can rise without demand changing. Explicit per-dish/channel menu-price overrides take precedence over the pass-through formula.

Example: if the reference recipe cost is $3.60, an ingredient change makes it $3.96, and the menu price is $12, then 100% pass-through proposes $12.36. With assumed elasticity −1, demand is multiplied by 12 / 12.36, about 0.9709. At 0% pass-through, price stays $12 and demand stays unchanged. Negative cost changes can propose price reductions and raise assumed demand. This is an illustrative calculation, not a result learned from the demo corpus.

## Limits and safety boundaries

Price elasticity is always labeled `owner_assumption`. A menu-price-history diagnostic reports when there is no within-series price variation; even with variation, the implementation does not claim causal identification. Different sensitivity assumptions can be explored without changing historical data. Substitution between dishes, competitors, promotions, capacity, waste and inventory are not modeled.

Scenarios are read-only. They do not change menu/catalog records, forecast selection, worker policy, alerts or actual receipts. They reject stale/non-ready snapshots, unknown/duplicate overrides, incompatible reference recipes and nonpositive or extreme menu changes. Menu prices must remain within 50%–200% of their baseline; elasticity is bounded to −5 through 0. Larger changes require a different model rather than extrapolation from this planner.

Ingredient evidence references approved invoice prices. An override is marked `owner_assumption`; that invoice is not evidence for the hypothetical price. Revenue less ingredient cost excludes fees, packaging, labor and rent and is not profit. Existing low/high volume scenarios are sensitivity analyses, not calibrated prediction intervals. The existing two website alert types keep their original policy and never report hypothetical pricing decisions as actual business events.

## API examples (PowerShell)

```powershell
$base = "http://127.0.0.1:8000"
$forecast = Invoke-RestMethod "$base/api/forecasts/recalculate" -Method Post `
  -ContentType "application/json" `
  -Body (@{ method = "regularized_poisson_v1" } | ConvertTo-Json)

$scenario = Invoke-RestMethod "$base/api/forecasts/$($forecast.id)/pricing-scenario" `
  -Method Post -ContentType "application/json" -Body (@{
    cost_pass_through_pct = "100"
    price_elasticity = "-1"
    ingredient_prices = @(@{ ingredient_id = "beef"; unit_cost = "4.72" })
  } | ConvertTo-Json -Depth 5)
$scenario.series | Format-Table dish_id, channel_id, scenario_menu_price, baseline_units, units
```

The endpoint also accepts `reference_date` and `menu_prices`, an array of `{ dish_id, channel_id, price }`. All money and quantities remain decimal strings. Use a ready forecast matching the current source-data version.

Verified restaurant registration, tenant isolation, OAuth consent and background mailbox ingestion are separate future work, described in [post-hackathon-plan.md](post-hackathon-plan.md). Entering an email address alone never grants inbox access.

## Calculation latency

The Poisson model is still trained with the same scikit-learn pipeline. During recursive prediction, its fitted one-hot categories, imputation statistics/indicators, scaling parameters, coefficients and exponential link are evaluated directly with NumPy. This avoids rebuilding ColumnTransformer/joblib output adapters for each tiny daily batch. A parity test compares every recursive batch against the original pipeline, including missing lags and unseen calendar months, within `1e-12` relative/absolute tolerance.

Each calculation shares a request-local cache across adaptive validation and the held-out evaluation. Longer predictions supply identical shorter prefixes; historical feature rows are reused only within the same immutable ledger snapshot. Statistical weekday estimates are computed once per series/weekday, and native thread limits cover the prediction loop instead of being rebuilt each day. No global forecast-data cache is shared across restaurants or changed ledgers. Existing versioned immutable snapshots continue to serve repeat requests.

On the unchanged demo corpus on this workstation, an unprofiled warm uncached Auto calculation fell from **8.438s to 1.004s**; an identical cached request took **0.003s**. These indicative single-run timings include calculation and the existing holdout evaluation, use isolated copies of the same corpus, and are not a hardware-independent latency guarantee. A fresh process still has one-time scientific-library import cost. See [performance-demo.json](../examples/forecasting/performance-demo.json).

When records change, a saved complete curve can remain visible as **Previous forecast · updating**, without displaying its old monthly totals as current. Default-policy upgrades are announced by the server; the UI does not infer a preference change from a snapshot implementation version. Automatic refresh uses the saved policy, while manual choices explicitly request a method. Browser verification observed a saved curve within 226ms after opening the tab; pricing changes use the existing lightweight scenario endpoint and do not refit the demand model.
