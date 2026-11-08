"""Forecast experiments must not read future targets or change the live ledger."""
from copy import deepcopy
from datetime import date, timedelta
import math

import pytest

from backend.marginguard import analytics
from backend.marginguard.db import connect
from backend.marginguard.forecast_benchmark import (
    BASELINE, BOOSTED, METHODS, NAIVE, POISSON, Panel, evaluate, features, load_panel, predict, score,
)
from backend.marginguard.seed import seed_demo


@pytest.fixture
def panel():
    start = date(2026, 1, 1)
    series = (("burger", "counter"), ("burger", "delivery"))
    observed = {(start + timedelta(days=i), *s): float(8 + (i % 7) + channel * 4)
                for i in range(56) for channel, s in enumerate(series)}
    return Panel(start, start + timedelta(days=55), series, observed, frozenset(),
                 {s: start for s in series}, 1, True)


def test_missing_features_are_distinguished_from_confirmed_zero(panel):
    day = panel.start + timedelta(days=20)
    key = (day - timedelta(days=7), *panel.series[0])
    history = dict(panel.observed)
    history.pop(key)
    assert math.isnan(features(day, panel.series[0], history, panel)[7])
    history[key] = 0.0
    assert features(day, panel.series[0], history, panel)[7] == 0.0


@pytest.mark.parametrize("method", METHODS)
def test_entire_future_target_change_cannot_change_any_prediction(panel, method):
    if method in (BOOSTED, POISSON):
        pytest.importorskip("sklearn")
    origin = panel.start + timedelta(days=28)
    changed = deepcopy(panel)
    changed.observed = {k: (v * 1000 if k[0] >= origin else v) for k, v in changed.observed.items()}
    original = predict(panel, origin, 28, method)
    assert original and predict(changed, origin, 28, method) == pytest.approx(original)
    assert all(math.isfinite(value) and value >= 0 for value in original.values())


@pytest.mark.parametrize("method", METHODS)
def test_known_future_closure_overrides_demand_without_training_on_it(panel, method):
    if method in (BOOSTED, POISSON):
        pytest.importorskip("sklearn")
    origin = panel.start + timedelta(days=35)
    key = (origin + timedelta(days=2), *panel.series[0])
    panel.observed.pop(key)
    panel.closed = frozenset({key})
    assert predict(panel, origin, 7, method)[key] == 0.0


def test_backtests_use_the_same_cases_and_do_not_promote_a_model(panel):
    panel.observed.pop((panel.start + timedelta(days=24), *panel.series[0]))
    report = evaluate(panel, methods=(BASELINE, NAIVE))
    assert report["is_demo"]
    assert len(report["horizons"][0]["folds"]) == 4
    assert report["horizons"][1]["evaluation_status"] == "limited_history"
    for horizon in report["horizons"]:
        assert horizon["automatic_promotion"] is False
        for fold in horizon["folds"]:
            assert fold["metrics"][BASELINE]["observations"] == fold["metrics"][NAIVE]["observations"]
            assert fold["scored_observations"] + fold["skipped_observations"] == fold["eligible_observations"]
            assert date.fromisoformat(fold["end"]) <= panel.end


def test_zero_demand_has_no_fabricated_percentage_error():
    assert score([(0, 0)]) == {"observations": 1, "mae": 0.0, "rmse": 0.0, "wape": None}
    assert score([])["mae"] is None
    assert score([(2, 4), (4, 2)])["mae"] == 2.0


def test_panel_loading_is_read_only_and_excludes_incomplete_dates(tmp_path, monkeypatch):
    path = tmp_path / "ledger.db"
    seed_demo(path)
    monkeypatch.setattr(analytics, "local_today", lambda owner: date(2026, 11, 7))
    with connect(path) as conn:
        before = list(conn.iterdump())
        conn.execute("PRAGMA query_only=ON")
        conn.execute("BEGIN")
        data = load_panel(conn)
        assert all(k[0] < date(2026, 11, 7) for k in data.observed)
        assert before == list(conn.iterdump())


@pytest.mark.parametrize("kwargs", [{"initial_days": 7}, {"step": 0}, {"horizons": (0,)}, {"methods": ("unknown",)}])
def test_invalid_backtest_policies_are_rejected(panel, kwargs):
    with pytest.raises(ValueError):
        evaluate(panel, **kwargs)
