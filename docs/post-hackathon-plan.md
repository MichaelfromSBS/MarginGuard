# MarginGuard: post-hackathon development

## Goal and current boundary

Build a working product with accountable forecasting and automatic supplier-document ingestion. Keep the existing fictional dataset unchanged. Model experiments use isolated imports of that same corpus. The app now exposes explicit model selection and a separate read-only pricing scenario; the default is the adaptive ensemble, with the weekday model retained as its conservative anchor.

Implemented: an offline forecast benchmark, shared prediction engine, two selectable fitted ML models, saved prediction metadata, matched holdout evaluation, worker policy retention and a cost/menu-price/demand scenario planner. Account registration and mailbox connectors remain subsequent implementation checkpoints. See [forecasting.md](forecasting.md) for the implemented feature.

## Forecasting: a measurable upgrade

The benchmark reads approved records, groups demand by local date/dish/channel, and distinguishes confirmed zero sales from incomplete, unknown or closed dates. It compares:

- Existing weekday averages, requiring four observations per applicable weekday.
- Seasonal naive: repeat the previous week's demand recursively.
- L2-regularized Poisson regression with one-hot calendar/catalog features and past demand features.
- Histogram gradient boosting with Poisson loss, pooled across dishes/channels.

Features are dish, channel, weekday, month, day of month, elapsed days, lags at one/seven/fourteen/twenty-eight days, rolling seven/twenty-eight-day means, previous matching-weekday means and observed-history count. Features only use earlier dates. Preprocessing is fitted on the training window. Random estimator early stopping is disabled for the boosted candidate. Future forecast lags use previous predictions rather than held-out actuals.

Use chronological expanding-origin backtests with seven- and twenty-eight-day horizons. Report MAE, RMSE, WAPE, exact common scored observations, skipped cases and fold counts. Do not choose hyperparameters on a final test period or use random train/test splitting. The existing ledger lacks full historical ingestion-time snapshots, so the report explicitly describes this as a retrospective simulation over currently approved records. See [scikit-learn's lag-feature evaluation example](https://scikit-learn.org/stable/auto_examples/applications/plot_time_series_lagged_features.html) and [Poisson regression](https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.PoissonRegressor.html).

### First reproducible result: unchanged fictional data

| Candidate | Seven-day MAE, four folds | Twenty-eight-day MAE, one fold |
| --- | ---: | ---: |
| Weekday average | 4.348764 | 4.408951 |
| Seasonal naive | 5.057692 | 5.438272 |
| Regularized Poisson | 4.420878 | 4.142417 |
| Poisson gradient boosting | 4.844240 | 4.827821 |

MAE is dish/channel units per evaluated day. Each column compares the same scored cases: 156 for the pooled seven-day folds and 162 for the twenty-eight-day fold. The month-length result has insufficient independent windows for a reliable model-promotion claim. These results are exploratory, specific to fictional data, and do not establish real restaurant accuracy. A larger model is not automatically better; the evaluation-stage default remained unchanged; the subsequent owner-requested default is now the adaptive ensemble.

The report is [benchmark-demo.json](../examples/forecasting/benchmark-demo.json). No uncertainty coverage or production-performance claims are implied. The existing low/high demand scenarios remain sensitivity scenarios.

### Run it

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-forecasting.lock.txt

# Optional: the same existing fixture corpus, explicitly imported into a separate DB.
.\.venv\Scripts\python.exe -m backend.marginguard.import_demo --database data/forecast-research.db

.\.venv\Scripts\python.exe -m backend.marginguard.forecast_benchmark `
  --database data/forecast-research.db `
  --output data/forecast-benchmark.json
```

The source database is read through a query-only snapshot. No AI calls, emails, forecast writes, owner alerts or training-data generation occur. The main app can run without the optional forecasting dependencies. The optional lock file records the tested scientific packages separately from the original app environment.

### Model serving: implemented foundation; remaining work

- Complete: shared demand estimators power both backtesting and live forecasts; Decimal-based revenue/recipe pricing is retained.
- Complete: explicit method, training version/cutoff, prediction origin, implementation/library version and immutable prediction snapshots; incompatible fitted-model versions cannot be attributed together.
- Complete: explicit experimental model selection and matched seven-day holdout MAE; adaptive ensemble is the default; weekday averages remain available and anchor the ensemble. Missing optional dependencies return an actionable error rather than silently substituting another method. No automatic promotion occurs.
- Predictions are refitted and cached on changed data/date/policy using retained method settings. Remaining: persisted estimator artifacts, a dedicated evaluation-history view and drift/error monitoring as outcomes arrive.
- Show calibrated prediction intervals only after implementing and evaluating them. Avoid presenting a model's arbitrary range or independent daily intervals as a calibrated monthly interval.

## Registration and email access are separate

Entering an email address identifies an account. It does not authorize reading that account's mailbox. Signing into the website and consenting to mailbox access are separate permissions, even if the same Google/Microsoft account is used for both.

Recommended owner experience:

1. Register/sign in and create the restaurant profile.
2. Open **Connect business inbox** and choose Google or Microsoft.
3. Approve read-only mailbox access in the provider's consent screen.
4. Choose an invoice label/folder and supplier filters.
5. The service finds new attachments and runs the existing extraction/validation pipeline in the background.
6. The owner reviews exceptions and can disconnect the inbox later.

A business address with a custom domain can be hosted by either provider, so its domain alone is not sufficient to choose a connector reliably. An alternative for other providers is a restaurant-specific forwarding address: the owner creates a forwarding rule once, and an inbound-email service delivers attachments to MarginGuard. It still requires that initial setup; an arbitrary typed address cannot confer mailbox access.

Google's [web-server OAuth flow](https://developers.google.com/identity/protocols/oauth2/web-server) supports consent and background access through tokens. Gmail's read-only scope is mailbox-wide; a chosen label is an application-side filter, not a provider-enforced limitation of that scope. Public distribution must account for the scope's [verification requirements](https://developers.google.com/workspace/gmail/api/auth/scopes).

## Next checkpoint: accounts and restaurant isolation

The hackathon application assumes a single restaurant. Before a hosted system accepts multiple owners:

- Add verified identity, sessions, restaurant ownership and access checks.
- Isolate documents, catalogs, sales, forecasts, jobs, model artifacts and connector state by restaurant.
- Add cross-restaurant authorization tests. Never accept a client-supplied restaurant ID as proof of access.
- Preserve the fictional demo separately from registered restaurants.
- Separate OAuth login permission from later incremental authorization for a mailbox.

This is a prerequisite for a public multi-restaurant email feature, rather than a cosmetic registration form on the single-restaurant database.

## Next checkpoint: automatic invoice ingestion

Use a provider adapter feeding the current persistent document queue:

Authorized mailbox → incremental message discovery → selected attachments → duplicate-safe document registration → existing AI extraction → business validation/review → approved ledger → forecasts and website alerts.

Provider-independent requirements:

- Store connection ownership, provider account, selected folder/label, sync cursor and safe status/error information.
- Store refresh tokens encrypted server-side, separately from frontend data; support revocation, expiry and reconnect flows. OAuth state must be tied to the initiating authenticated session.
- Fetch network data outside ledger transactions. Retry transient failures with bounded backoff and preserve durable sync state.
- Use a unique connection/message/attachment key plus the existing document hashes and business identifiers. Move cursors forward only after affected items are durably recorded for processing.
- Apply configured sender/type/size filters. Preserve source provenance so an owner can trace a document back to its message.
- Keep suspicious, unsupported or invalid inputs in review. Mail content and attachments remain untrusted inputs to AI and parsers.
- Never send, delete, archive or mark messages read as part of invoice import. Owner notifications remain inside the website.
- Show sync health and last successful processing time. Losing authorization must not look like a healthy but empty mailbox.

For Gmail, use message/attachment endpoints and history-based incremental sync, with bounded resync when a history cursor expires; see [Gmail synchronization](https://developers.google.com/workspace/gmail/api/guides/sync). For Microsoft 365, use the equivalent folder/message APIs and [Graph delta queries](https://learn.microsoft.com/en-us/graph/api/message-delta). Start with bounded polling; add push/webhook delivery after the service is hosted and authenticated.

Activation requires application OAuth credentials, registered redirect URLs and the owner consenting to connect a mailbox. No mailbox has been connected, read or modified during this implementation step. Existing `.env` values were preserved.

Email invoice ingestion automates purchasing inputs. Continuous sales ingestion additionally needs a POS connector or supported emailed sales exports; supplier invoices alone do not provide customer sales.

## Resume evidence to build toward

Prioritize demonstrable behavior: reproducible time-series evaluation, documented model choice, restart-safe ingestion, incremental synchronization, account isolation, audit provenance and clear failure/review states. Report accuracy improvements only with the actual dataset, horizon and evaluation method. OAuth ingestion and model serving should appear as completed work only after their end-to-end checkpoints pass.
