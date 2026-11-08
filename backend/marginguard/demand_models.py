"""Shared coverage-aware demand estimators used by serving and backtesting."""
from collections import defaultdict
from contextlib import nullcontext
from dataclasses import dataclass
from datetime import date, timedelta
import math
import os
import statistics

from . import analytics
from .ingestion import restaurant_record


def first_offered(conn, dish_id, channel_id):
    price = conn.execute("SELECT MIN(effective_date) FROM menu_prices WHERE dish_id=? AND channel_id=?", (dish_id, channel_id)).fetchone()[0]
    recipe = conn.execute("SELECT MIN(effective_date) FROM recipe_versions WHERE dish_id=?", (dish_id,)).fetchone()[0]
    return max(price, recipe) if price and recipe else "9999-12-31"

BASELINE = "weekday_average_v1"
NAIVE = "seasonal_naive_v1"
BOOSTED = "poisson_gradient_boosting_v1"
POISSON = "regularized_poisson_v1"
RECENT = "recency_weekday_v1"
ADAPTIVE = "adaptive_ensemble_v1"
METHODS = (BASELINE, NAIVE, POISSON, BOOSTED, RECENT, ADAPTIVE)


@dataclass
class Panel:
    start: date
    end: date
    series: tuple
    observed: dict
    closed: frozenset
    offered: dict
    source_data_version: int
    is_demo: bool


def load_panel(conn, as_of=None):
    """Coverage defines eligible labels; unknown days never become zero demand."""
    owner = restaurant_record(conn)
    last_finished = (as_of or analytics.local_today(owner)) - timedelta(days=1)
    rows = conn.execute("SELECT MIN(date),MAX(date) FROM daily_coverage WHERE date<=?", (last_finished.isoformat(),)).fetchone()
    if not rows[0]:
        raise ValueError("No finished-day coverage is available for evaluation.")
    start, end = date.fromisoformat(rows[0]), date.fromisoformat(rows[1])
    if (end - start).days > 3650:
        raise ValueError("Limit the research ledger to ten years of daily history.")
    series = tuple((d[0], c[0]) for d in conn.execute("SELECT id FROM dishes ORDER BY id")
                   for c in conn.execute("SELECT id FROM channels ORDER BY id"))
    offered = {s: date.fromisoformat(first_offered(conn, *s)) for s in series}
    coverage = analytics.coverage_summary(conn, start, end)
    states = {(date.fromisoformat(r["date"]), r["channel_id"]): r["status"] for r in coverage["days"]}
    counts = {}
    for row in analytics.sales_rows(conn, start, end):
        key = (date.fromisoformat(row["local_date"]), row["dish_id"], row["channel_id"])
        counts[key] = counts.get(key, 0.0) + float(row["quantity"])
    observed, closed = {}, set()
    for day in analytics.dates(start, end):
        for dish, channel in series:
            if day < offered[(dish, channel)]:
                continue
            key = (day, dish, channel)
            if states[(day, channel)] == "complete":
                observed[key] = counts.get(key, 0.0)
            elif states[(day, channel)] == "closed":
                closed.add(key)
    return Panel(start, end, series, observed, frozenset(closed), offered,
                 owner["data_version"], bool(owner["is_demo"]))


def average(values):
    values = [v for v in values if v is not None and math.isfinite(v)]
    return statistics.fmean(values) if values else math.nan


def features(day, series, history, panel):
    """Every sales feature uses a strictly earlier local date."""
    dish, channel = series
    dishes = sorted({s[0] for s in panel.series})
    channels = sorted({s[1] for s in panel.series})
    def lag(offset):
        return history.get((day - timedelta(days=offset), dish, channel), math.nan)
    return [dishes.index(dish), channels.index(channel), day.weekday(), day.month,
            day.day, (day - panel.start).days,
            lag(1), lag(7), lag(14), lag(28),
            average(lag(i) for i in range(1, 8)),
            average(lag(i) for i in range(1, 29)),
            average(lag(i) for i in (7, 14, 21, 28)),
            sum(math.isfinite(lag(i)) for i in range(1, 29))]


def poisson_predictor(model):
    """Compile the fitted public preprocessing parameters into a NumPy prediction path.

    This is the same one-hot/impute/scale/log-link calculation, without rebuilding
    ColumnTransformer/joblib output adapters for each tiny six-row daily batch.
    """
    import numpy as np
    transform, regressor = model.steps[0][1], model.steps[1][1]
    encoder = transform.named_transformers_['categorical']
    numeric = transform.named_transformers_['numeric']
    imputer, scaler = numeric.steps[0][1], numeric.steps[1][1]
    categories = encoder.categories_
    indicators = imputer.indicator_.features_
    def predict(x):
        one_hot = np.concatenate([(x[:, i, None] == values).astype(float) for i, values in enumerate(categories)], axis=1)
        values = x[:, 4:]
        missing = np.isnan(values)
        filled = np.where(missing, imputer.statistics_, values)
        if len(indicators):
            filled = np.concatenate([filled, missing[:, indicators].astype(float)], axis=1)
        scaled = (filled - scaler.mean_) / scaler.scale_
        return np.exp(np.concatenate([one_hot, scaled], axis=1) @ regressor.coef_ + regressor.intercept_)
    return predict


def predict(panel, origin, horizon, method, *, history_weeks=8, minimum=4, diagnostics=None, cache=None):
    """Predict from one fixed ledger snapshot; any cache belongs to that request only."""
    if method not in METHODS:
        raise ValueError("Unknown forecasting method.")
    if horizon < 1 or horizon > 62 or history_weeks < 4 or minimum < 1:
        raise ValueError("Unsupported evaluation policy.")
    if method == ADAPTIVE:
        from .adaptive_forecast import predict as adaptive_predict
        return adaptive_predict(panel, origin, horizon, history_weeks=history_weeks, minimum=minimum, diagnostics=diagnostics, cache=cache)
    cache_key = (method, origin, history_weeks, minimum)
    if cache is not None and cache_key in cache and cache[cache_key]['horizon'] >= horizon:
        stop = origin + timedelta(days=horizon)
        return {key: value for key, value in cache[cache_key]['predictions'].items() if key[0] < stop}
    start = max(panel.start, origin - timedelta(weeks=history_weeks))
    observed = {k: v for k, v in panel.observed.items() if start <= k[0] < origin}
    # A known closure is zero for lag features, but is never a training target.
    history = {k: 0.0 for k in panel.closed if k[0] < origin}
    history.update({k: v for k, v in panel.observed.items() if k[0] < origin})
    model = None
    if method in (BOOSTED, POISSON):
        training = sorted(observed)
        if not training or sum(observed.values()) <= 0:
            return {}
        # Bound native-library thread allocation before their first import.
        # A small restaurant panel does not benefit from machine-wide pools.
        for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
            os.environ.setdefault(name, "1")
        try:
            import numpy as np
            from sklearn.ensemble import HistGradientBoostingRegressor
            from threadpoolctl import threadpool_limits
        except ImportError as exc:
            raise ValueError("Install requirements-forecasting.lock.txt to run fitted forecasting models.") from exc
        feature_key = ('training_features', origin, history_weeks)
        if cache is not None and feature_key in cache:
            x_train = cache[feature_key]
        else:
            feature_rows = []
            for key in training:
                row_key = ('actual_features', key)
                if cache is not None and row_key in cache:
                    row = cache[row_key]
                else:
                    row = features(key[0], key[1:], history, panel)
                    if cache is not None:
                        cache[row_key] = row
                feature_rows.append(row)
            x_train = np.asarray(feature_rows, dtype=float)
            if cache is not None:
                cache[feature_key] = x_train
        # Short histories can have no usable lag-28 observations. Drop such
        # columns using training data only; never substitute a false zero.
        active_columns = ~np.isnan(x_train).all(axis=0)
        # Disable the estimator's random validation split for time-series data.
        if method == BOOSTED:
            model = HistGradientBoostingRegressor(loss="poisson", learning_rate=.05,
                max_iter=120, max_leaf_nodes=15, min_samples_leaf=10, l2_regularization=1,
                categorical_features=np.asarray([True, True, True, True] + [False] * 10)[active_columns],
                early_stopping=False, random_state=42)
        else:
            from sklearn.compose import ColumnTransformer
            from sklearn.impute import SimpleImputer
            from sklearn.linear_model import PoissonRegressor
            from sklearn.pipeline import make_pipeline
            from sklearn.preprocessing import OneHotEncoder, StandardScaler
            transform = ColumnTransformer([
                ("categorical", OneHotEncoder(handle_unknown="ignore", sparse_output=False), list(range(4))),
                ("numeric", make_pipeline(SimpleImputer(add_indicator=True), StandardScaler()),
                 list(range(4, int(active_columns.sum()))))])
            model = make_pipeline(transform, PoissonRegressor(alpha=.2, max_iter=1000))
        with threadpool_limits(limits=1):
            model.fit(x_train[:, active_columns], np.asarray([observed[k] for k in training], dtype=float))
    weekday_means = {}
    if method in (BASELINE, RECENT):
        samples = defaultdict(list)
        for key, value in observed.items():
            samples[(*key[1:], key[0].weekday())].append((key[0], value))
        for key, values in samples.items():
            if len(values) < minimum:
                continue
            if method == BASELINE:
                weekday_means[key] = statistics.fmean(value for _, value in values)
            else:
                weights = [2 ** (-(origin - day).days / 14) for day, _ in values]
                weekday_means[key] = sum(value * weight for (_, value), weight in zip(values, weights)) / sum(weights)
    direct_predict = poisson_predictor(model) if model is not None and method == POISSON else model.predict if model is not None else None
    result = {}
    with threadpool_limits(limits=1) if model is not None else nullcontext():
        for day in analytics.dates(origin, origin + timedelta(days=horizon - 1)):
            eligible = [s for s in panel.series if day >= panel.offered[s]]
            learned = {}
            if model is not None and eligible:
                x = np.asarray([features(day, s, history, panel) for s in eligible], dtype=float)
                learned = dict(zip(eligible, direct_predict(x[:, active_columns])))
            daily = {}
            for s in eligible:
                key = (day, *s)
                if key in panel.closed:
                    value = 0.0
                elif method in (BASELINE, RECENT):
                    value = weekday_means.get((*s, day.weekday()))
                elif method == NAIVE:
                    value = history.get((day - timedelta(days=7), *s))
                else:
                    value = float(learned[s])
                if value is not None:
                    if not math.isfinite(value) or value < 0:
                        raise ValueError("A candidate produced an invalid demand estimate.")
                    result[key] = daily[key] = value
            # Forecast recursively: future lags use predictions, never held-out actuals.
            history.update(daily)
    if cache is not None:
        cache[cache_key] = {'horizon': horizon, 'predictions': result}
    return result
