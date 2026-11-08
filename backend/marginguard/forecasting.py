"""Versioned planning snapshots with selectable, coverage-aware demand models."""
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal, ROUND_DOWN
import hashlib
import json

from .analytics import (CENT, ZERO, coverage_summary, dates, decimal_text,
                        dish_cost, local_today, menu_price, sales_rows)
from .errors import DomainError
from .ingestion import identifier, insert, now, restaurant_record
from .schemas import ForecastResponse
from . import demand_models

METHOD = "weekday_average_v1"
DEFAULT_POLICY_VERSION = "adaptive_default_v1"
ASSUMPTIONS = [
    "Demand is a weekday average of approved units by dish/channel using complete past local days only.",
    "Complete days without a sale are zero observations only after the dish's first effective menu price and recipe.",
    "Partial, unknown and explicitly closed training days are excluded; recorded unusual days are retained.",
    "The horizon is the next calendar month. Future dates without a closure record are assumed open.",
    "Current effective menu prices, ingredient prices and recipes are held constant across the horizon, with no assumed discounts.",
    "Prices are selected by effective date from currently approved records; this is not a reconstruction of what was known at that historical instant.",
    "Ingredient consumption cost excludes stock on hand, waste, purchase scheduling, package rounding, freight, tax, labor and rent.",
    "Low/high results are volume sensitivity scenarios, not calibrated prediction intervals. Menu-price demand effects are explored separately in the pricing scenario.",
    "Money uses half-up cents. Rounded row allocations reconcile to restaurant totals; units retain eight decimals.",
]


def default_request(conn, as_of=None):
    """Keep the last successfully selected policy across worker refreshes/restarts."""
    from .schemas import ForecastRequest
    row = conn.execute("SELECT value FROM worker_state WHERE key='forecast_selection'").fetchone()
    if row is None:
        row = conn.execute("SELECT assumptions_json FROM forecast_runs ORDER BY created_at DESC,rowid DESC LIMIT 1").fetchone()
    saved = json.loads(row[0]) if row else {}
    marker = conn.execute("SELECT value FROM worker_state WHERE key='forecast_default_policy'").fetchone()
    if marker is None or marker[0] != DEFAULT_POLICY_VERSION:
        saved['method'] = demand_models.ADAPTIVE
    policy = {key: saved[key] for key in ForecastRequest.model_fields if key in saved and key != "as_of"}
    return ForecastRequest(**policy, as_of=as_of)


def activate(conn, result, request):
    """Selection is separate from immutable creation time, including cache hits."""
    for key, value in [("forecast_selection", request.model_dump_json(exclude={"as_of"})), ("active_forecast_id", result.id), ("forecast_default_policy", DEFAULT_POLICY_VERSION)]:
        conn.execute("INSERT INTO worker_state(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
    return result


def model_predictions(conn, as_of, horizon_end, request, cache=None):
    """Bridge the rest of this month recursively; never use future actual sales."""
    try:
        panel = demand_models.load_panel(conn, as_of)
    except ValueError:
        return {}, None, {}
    end_text = horizon_end.isoformat()
    closed_days = {r[0] for r in conn.execute("SELECT date FROM restaurant_calendar WHERE is_open=0 AND date BETWEEN ? AND ?", (as_of.isoformat(), end_text))}
    closed_channels = {(r[0], r[1]) for r in conn.execute("SELECT date,channel_id FROM daily_coverage WHERE status='closed' AND date BETWEEN ? AND ?", (as_of.isoformat(), end_text))}
    panel.closed = panel.closed | frozenset((d, *s) for d in dates(as_of, horizon_end) for s in panel.series
        if d.isoformat() in closed_days or (d.isoformat(), s[1]) in closed_channels)
    diagnostics = {}
    try:
        predictions = demand_models.predict(panel, as_of, (horizon_end - as_of).days + 1, request.method,
            history_weeks=request.history_weeks, minimum=request.min_observations, diagnostics=diagnostics, cache=cache)
    except ValueError as exc:
        raise DomainError("forecast_model_unavailable", str(exc), 503) from exc
    return predictions, panel, diagnostics


def selected_evaluation(panel, as_of, request, evaluation, cache=None):
    evaluation["selected_method"] = request.method
    if request.method == METHOD:
        evaluation["selected_method_mae"] = evaluation["weekday_average_mae"]
        return
    if panel is None:
        return
    cut = as_of - timedelta(days=7)
    predicted = demand_models.predict(panel, cut, 7, request.method,
        history_weeks=request.history_weeks, minimum=request.min_observations, cache=cache)
    baseline = demand_models.predict(panel, cut, 7, METHOD,
        history_weeks=request.history_weeks, minimum=request.min_observations, cache=cache)
    naive = demand_models.predict(panel, cut, 7, demand_models.NAIVE, cache=cache)
    eligible = {k for k in panel.observed if cut <= k[0] < as_of}
    matched = eligible & predicted.keys() & baseline.keys() & naive.keys()
    evaluation["observations"] = len(matched)
    evaluation["status"] = "ready" if matched and len(matched) == len(eligible) else "insufficient_history"
    for name, predictions in [("selected_method_mae", predicted), ("weekday_average_mae", baseline), ("seasonal_naive_mae", naive)]:
        evaluation[name] = decimal_text(sum((abs(Decimal(str(panel.observed[k])) - Decimal(str(predictions[k]))) for k in matched), ZERO) / len(matched)) if matched else None


def next_month(as_of):
    start = (as_of.replace(day=28) + timedelta(days=4)).replace(day=1)
    end = (start.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    return start, end


def rounded_allocations(values, target=None):
    """Allocate residual cents by largest fractional remainder, stable on ties."""
    if not values:
        return []
    target = Decimal(decimal_text(sum(values, ZERO), money=True)) if target is None else target
    rounded = [v.quantize(CENT, rounding=ROUND_DOWN) for v in values]
    remaining = int((target - sum(rounded, ZERO)) / CENT)
    ranking = sorted(range(len(values)), key=lambda i: (-(values[i] - rounded[i]), i))
    for index in range(abs(remaining)):
        rounded[ranking[index % len(ranking)]] += CENT if remaining > 0 else -CENT
    return rounded


def demand_inputs(conn, start, end):
    coverage = coverage_summary(conn, start, end)
    complete = {(r["date"], r["channel_id"]) for r in coverage["days"] if r["status"] == "complete"}
    quantities = defaultdict(lambda: ZERO)
    for row in sales_rows(conn, start, end):
        quantities[(row["local_date"], row["dish_id"], row["channel_id"])] += Decimal(row["quantity"])
    return coverage, complete, quantities


def first_offered(conn, dish_id, channel_id):
    return demand_models.first_offered(conn, dish_id, channel_id)


def estimates(start, end, dish_id, channel_id, complete, quantities, offered, minimum):
    result = []
    for weekday in range(7):
        samples = [d.isoformat() for d in dates(start, end) if d.weekday() == weekday and d.isoformat() >= offered and (d.isoformat(), channel_id) in complete]
        mean = sum((quantities[(d, dish_id, channel_id)] for d in samples), ZERO) / len(samples) if len(samples) >= minimum else None
        result.append({"weekday": weekday, "sample_dates": samples, "mean_units": decimal_text(mean) if mean is not None else None})
    return result


def evaluate(conn, as_of, request, dishes, channels):
    cut = as_of - timedelta(days=7)
    start, end = cut - timedelta(weeks=request.history_weeks), as_of - timedelta(days=1)
    _, complete, quantities = demand_inputs(conn, start, end)
    errors, naive_errors = [], []
    expected = 0
    for dish in dishes:
        for channel in channels:
            offered = first_offered(conn, dish["id"], channel["id"])
            fitted = estimates(start, cut - timedelta(days=1), dish["id"], channel["id"], complete, quantities, offered, request.min_observations)
            for day in dates(cut, end):
                key = (day.isoformat(), channel["id"])
                if key not in complete or day.isoformat() < offered:
                    continue
                expected += 1
                previous = day - timedelta(days=7)
                prediction = fitted[day.weekday()]["mean_units"]
                if prediction is None or (previous.isoformat(), channel["id"]) not in complete or previous.isoformat() < offered:
                    continue
                actual = quantities[(day.isoformat(), dish["id"], channel["id"])]
                errors.append(abs(actual - Decimal(prediction)))
                naive_errors.append(abs(actual - quantities[(previous.isoformat(), dish["id"], channel["id"])]))
    return {"status": "ready" if errors and len(errors) == expected else "insufficient_history",
            "holdout": {"start": cut, "end": end}, "observations": len(errors),
            "weekday_average_mae": decimal_text(sum(errors, ZERO) / len(errors)) if errors else None,
            "seasonal_naive_mae": decimal_text(sum(naive_errors, ZERO) / len(naive_errors)) if naive_errors else None,
            "assumptions": ["Final seven past local days are withheld; training ends before the holdout starts.",
                            "MAE is units per dish/channel/day, evaluated on matched complete days for both methods.",
                            "Insufficient-history evaluations may show a partial matched sample; they are not full-window evaluations.",
                            "Seven-day performance is not monthly predictive accuracy; fictional demo results do not validate real-world performance."]}


def calculate(conn, request):
    owner = restaurant_record(conn)
    as_of = request.as_of or local_today(owner)
    horizon_start, horizon_end = next_month(as_of)
    start, end = as_of - timedelta(weeks=request.history_weeks), as_of - timedelta(days=1)
    policy = {**request.model_dump(mode="json"), "as_of": as_of.isoformat(), "source_data_version": owner["data_version"], "implementation_version": 4}
    cache_key = hashlib.sha256(json.dumps(policy, sort_keys=True).encode()).hexdigest()
    cached = conn.execute("SELECT run_id FROM forecast_snapshots WHERE cache_key=?", (cache_key,)).fetchone()
    if cached:
        return activate(conn, get_forecast(conn, cached["run_id"]), request)
    coverage, complete, quantities = demand_inputs(conn, start, end)
    prediction_cache = {}
    predictions, panel, diagnostics = model_predictions(conn, as_of, horizon_end, request, prediction_cache) if request.method != METHOD else ({}, None, {})
    assumptions = list(ASSUMPTIONS)
    if request.method != METHOD:
        assumptions[0] = "Demand uses " + request.method + "; pooled calendar and strictly past demand features, recursively predicted across the current-month gap and next month."
        assumptions.append("Additional models are experimental; no automatic accuracy improvement or model promotion is claimed.")
    if request.method == demand_models.ADAPTIVE:
        assumptions[0] = "Adaptive demand combines models per dish/channel and lead-time bucket using chronological validation, with a weekday-average anchor."
        assumptions.extend(diagnostics.get('assumptions', []))
    dishes = [dict(r) for r in conn.execute("SELECT * FROM dishes ORDER BY id")]
    channels = [dict(r) for r in conn.execute("SELECT * FROM channels ORDER BY id")]
    costs = {d["id"]: dish_cost(conn, d["id"], as_of) for d in dishes}
    calendar = {r["date"]: r["is_open"] for r in conn.execute("SELECT date,is_open FROM restaurant_calendar WHERE date BETWEEN ? AND ?", (horizon_start.isoformat(), horizon_end.isoformat()))}
    closed = {(r["date"], r["channel_id"]) for r in conn.execute("SELECT date,channel_id FROM daily_coverage WHERE status='closed' AND date BETWEEN ? AND ?", (horizon_start.isoformat(), horizon_end.isoformat()))}
    series, daily, raw_revenues, raw_costs, limitations = [], [], [], [], []
    ingredient_quantities = defaultdict(lambda: ZERO)
    ingredient_inputs = {}
    if not dishes or not channels:
        limitations.append("Configure dishes and channels before forecasting.")
    for dish in dishes:
        cost = costs[dish["id"]]
        for channel in channels:
            price = menu_price(conn, dish["id"], channel["id"], as_of)
            fitted = estimates(start, end, dish["id"], channel["id"], complete, quantities, first_offered(conn, dish["id"], channel["id"]), request.min_observations)
            rows = []
            for day in dates(horizon_start, horizon_end):
                is_open = calendar.get(day.isoformat(), 1) == 1 and (day.isoformat(), channel["id"]) not in closed
                mean = fitted[day.weekday()]["mean_units"]
                if request.method != METHOD:
                    value = predictions.get((day, dish["id"], channel["id"]))
                    mean = decimal_text(Decimal(str(value))) if value is not None and mean is not None else None
                rows.append({"date": day, "dish_id": dish["id"], "channel_id": channel["id"], "is_open": is_open,
                             "units": mean if is_open else "0"})
            missing = sorted({r["date"].weekday() for r in rows if r["units"] is None})
            issues = ([f"Need {request.min_observations} complete observations for weekday {w} (Monday=0)." for w in missing]
                      + cost["limitations"] + (["No current menu price for this channel."] if price is None else []))
            status = "insufficient_history" if missing else "missing_inputs" if issues else "ready"
            units = sum((Decimal(r["units"]) for r in rows), ZERO) if not missing else None
            row = {"dish_id": dish["id"], "channel_id": channel["id"], "status": status,
                   "units": decimal_text(units) if units is not None else None, "revenue": None, "ingredient_cost": None,
                   "menu_price": price["price"] if price else None, "recipe_version_id": cost["recipe_version_id"],
                   "weekday_estimates": fitted, "limitations": issues}
            if status == "ready":
                raw_revenues.append(units * Decimal(price["price"]))
                raw_costs.append(units * sum((Decimal(i["extended_cost"]) for i in cost["ingredients"]), ZERO))
                for ingredient in cost["ingredients"]:
                    key = ingredient["ingredient_id"]
                    ingredient_quantities[key] += units * Decimal(ingredient["quantity"])
                    ingredient_inputs[key] = ingredient
            else:
                raw_revenues.append(ZERO)
                raw_costs.append(ZERO)
                limitations.extend(f"{dish['id']}/{channel['id']}: {issue}" for issue in issues)
            series.append(row)
            daily.extend(rows)
    ready = bool(series) and all(s["status"] == "ready" for s in series)
    ingredients, scenarios = [], []
    total_units = sum((Decimal(s["units"]) for s in series if s["units"] is not None), ZERO)
    revenue, total_cost = None, None
    if ready:
        raw_ingredient_costs = []
        for key in sorted(ingredient_quantities):
            source = ingredient_inputs[key]
            quantity = decimal_text(ingredient_quantities[key])
            raw_ingredient_costs.append(Decimal(quantity) * Decimal(source["unit_cost"]))
            ingredients.append({"ingredient_id": key, "quantity": quantity, "base_unit": source["base_unit"],
                                "unit_cost": source["unit_cost"], "cost": "0.00", "evidence": source["evidence"]})
        revenue = Decimal(decimal_text(sum(raw_revenues, ZERO), money=True))
        total_cost = Decimal(decimal_text(sum(raw_ingredient_costs, ZERO), money=True))
        for row, value, cost in zip(series, rounded_allocations(raw_revenues, revenue), rounded_allocations(raw_costs, total_cost)):
            row["revenue"], row["ingredient_cost"] = decimal_text(value, money=True), decimal_text(cost, money=True)
        for row, cost in zip(ingredients, rounded_allocations(raw_ingredient_costs, total_cost)):
            row["cost"] = decimal_text(cost, money=True)
        sensitivity = Decimal(request.sensitivity_pct) / 100
        for name, multiplier in [("low", 1 - sensitivity), ("base", Decimal("1")), ("high", 1 + sensitivity)]:
            scenarios.append({"name": name, "volume_multiplier": decimal_text(multiplier), "units": decimal_text(total_units * multiplier),
                              "revenue": decimal_text(revenue * multiplier, money=True), "ingredient_cost": decimal_text(total_cost * multiplier, money=True)})
    run_id, stamp = identifier("forecast"), now()
    metrics = []
    for name, label, value, unit in [("units", "Projected units", total_units if ready else None, "units"),
                                     ("revenue", "Projected net item revenue", revenue, "USD"),
                                     ("ingredient_cost", "Projected ingredient consumption cost", total_cost, "USD")]:
        metrics.append({"id": f"forecast.{name}", "label": label, "value": decimal_text(value, money=unit == "USD") if value is not None else None,
                        "unit": unit, "kind": "projected", "period": {"start": horizon_start, "end": horizon_end}, "as_of": stamp,
                        "coverage": "complete" if ready else "insufficient_history", "source_data_version": owner["data_version"],
                        "evidence": [{"kind": "forecast_run", "record_id": run_id}], "assumptions": assumptions})
    evaluation = evaluate(conn, as_of, request, dishes, channels)
    selected_evaluation(panel, as_of, request, evaluation, prediction_cache)
    metadata = {"implementation_version": 4, "training_data_version": owner["data_version"],
                "training_cutoff": end.isoformat(), "prediction_origin": as_of.isoformat(),
                "refit_policy": "Refit from approved history for each new data version/date/policy; immutable predictions are cached.",
                "elasticity_fitted": False}
    if diagnostics:
        metadata['adaptive'] = diagnostics
    if request.method != METHOD:
        from importlib.metadata import version, PackageNotFoundError
        try:
            metadata["scikit_learn_version"] = version("scikit-learn")
        except PackageNotFoundError:
            metadata["scikit_learn_version"] = None
    result = ForecastResponse.model_validate({"id": run_id, "status": "ready" if ready else "insufficient_history",
        "horizon": {"start": horizon_start, "end": horizon_end}, "method": request.method, "source_data_version": owner["data_version"],
        "created_at": stamp, "metrics": metrics, "assumptions": assumptions, "model_metadata": metadata,
        "as_of": as_of, "training_period": {"start": start, "end": end}, "training_coverage": coverage,
        "series": series, "daily": daily, "ingredients": ingredients, "scenarios": scenarios,
        "evaluation": evaluation, "limitations": limitations})
    insert(conn, "forecast_runs", id=run_id, horizon_start=horizon_start.isoformat(), horizon_end=horizon_end.isoformat(),
           status=result.status, method=request.method, source_data_version=owner["data_version"], assumptions_json=json.dumps(policy), created_at=stamp)
    insert(conn, "forecast_snapshots", run_id=run_id, cache_key=cache_key, as_of_date=as_of.isoformat(), response_json=result.model_dump_json())
    if ready:
        for row in series:
            insert(conn, "forecast_values", id=identifier("forecast_value"), run_id=run_id,
                   **{key: row[key] for key in ["dish_id", "channel_id", "units", "revenue", "ingredient_cost"]})
    return activate(conn, result, request)


def get_forecast(conn, run_id):
    row = conn.execute("SELECT r.*,s.response_json FROM forecast_runs r LEFT JOIN forecast_snapshots s ON s.run_id=r.id WHERE r.id=?", (run_id,)).fetchone()
    if row is None:
        raise DomainError("forecast_not_found", "Forecast does not exist.", 404)
    if row["response_json"] is None:
        raise DomainError("forecast_snapshot_unavailable", "This legacy forecast has no checkpoint-3 calculation snapshot. Recalculate it.", 409)
    result = ForecastResponse.model_validate_json(row["response_json"])
    result.status = row["status"]
    if result.source_data_version != restaurant_record(conn)["data_version"] or result.status == "pending":
        result.status = "pending"
        result.limitations.append("Saved values use an older data version. Recalculate before using them for current planning.")
    return result


def list_forecasts(conn, limit, offset):
    total = conn.execute("SELECT COUNT(*) FROM forecast_snapshots").fetchone()[0]
    rows = conn.execute("SELECT r.id FROM forecast_runs r JOIN forecast_snapshots s ON s.run_id=r.id ORDER BY r.created_at DESC,r.rowid DESC LIMIT ? OFFSET ?", (limit, offset))
    return {"items": [get_forecast(conn, r["id"]) for r in rows.fetchall()], "total": total, "limit": limit, "offset": offset}


def latest_forecast(conn, as_of):
    def current_policy(result):
        marker = conn.execute("SELECT value FROM worker_state WHERE key='forecast_default_policy'").fetchone()
        if marker is None or marker[0] != DEFAULT_POLICY_VERSION:
            result.status = 'pending'
            result.limitations.append('Forecast defaults changed. Refresh using the current saved policy.')
        return result
    active = conn.execute("SELECT s.run_id FROM forecast_snapshots s JOIN worker_state w ON w.key='active_forecast_id' AND w.value=s.run_id WHERE s.as_of_date=?", (as_of.isoformat(),)).fetchone()
    if active:
        return current_policy(get_forecast(conn, active["run_id"]))
    row = conn.execute("SELECT r.id FROM forecast_runs r JOIN forecast_snapshots s ON s.run_id=r.id WHERE s.as_of_date=? ORDER BY r.created_at DESC,r.rowid DESC LIMIT 1", (as_of.isoformat(),)).fetchone()
    return current_policy(get_forecast(conn, row["id"])) if row else None
