"""Adaptive selection must validate chronologically and retain a safe baseline."""
from copy import deepcopy
from datetime import date, timedelta
import math

import pytest

from backend.marginguard import demand_models as models
from backend.marginguard.adaptive_forecast import choose_weights


@pytest.fixture
def panel():
    start = date(2026, 1, 1)
    series = (('burger', 'in_store'), ('soup', 'delivery'))
    values = {(start + timedelta(days=i), *s): float(10 + i // 14 + i % 7 + j * 5)
              for i in range(84) for j, s in enumerate(series)}
    return models.Panel(start, start + timedelta(days=83), series, values, frozenset(), {s: start for s in series}, 1, True)


def cases(winners, n=42):
    return [{'origin': str(i // 7), 'actual': 10,
             'predictions': {models.BASELINE: 15, models.RECENT: winners[0], models.NAIVE: winners[1]}}
            for i in range(n)]


def test_clear_winner_and_blend_weights_are_convex_and_baseline_anchored():
    clear = choose_weights(cases((10, 14)), [models.BASELINE, models.RECENT, models.NAIVE])
    assert clear['reason'] == 'preferred_model'
    assert clear['weights'][models.RECENT] > clear['weights'][models.BASELINE] > 0
    blended = choose_weights(cases((11, 11.1)), [models.BASELINE, models.RECENT, models.NAIVE])
    assert blended['reason'] == 'validation_blend'
    assert len(blended['weights']) == 3
    assert sum(blended['weights'].values()) == pytest.approx(1)
    assert all(0 <= weight <= 1 for weight in blended['weights'].values())


def test_limited_validation_or_competitive_baseline_stays_baseline():
    assert choose_weights(cases((10, 10), 7), [models.BASELINE, models.RECENT])['weights'] == {models.BASELINE: 1}
    rows = cases((20, 18))
    assert choose_weights(rows, [models.BASELINE, models.RECENT, models.NAIVE])['reason'] == 'baseline_competitive'


def test_candidates_with_missing_validation_cases_cannot_game_the_score():
    rows = cases((10, 12))
    for row in rows[4:]:
        row['predictions'].pop(models.RECENT)
    result = choose_weights(rows, [models.BASELINE, models.RECENT, models.NAIVE])
    assert models.RECENT not in result['mae']
    assert result['observations'] == len(rows)


def without_ml(monkeypatch):
    original = models.predict
    def limited(panel, origin, horizon, method, **kwargs):
        if method in (models.POISSON, models.BOOSTED):
            raise ValueError('Optional model unavailable')
        return original(panel, origin, horizon, method, **kwargs)
    monkeypatch.setattr(models, 'predict', limited)
    return limited


def test_future_sales_cannot_change_predictions_or_selector_weights(panel, monkeypatch):
    predict = without_ml(monkeypatch)
    origin = panel.start + timedelta(days=56)
    altered = deepcopy(panel)
    altered.observed = {k: (v * 1000 if k[0] >= origin else v) for k, v in panel.observed.items()}
    a, b = {}, {}
    first = predict(panel, origin, 28, models.ADAPTIVE, diagnostics=a)
    second = predict(altered, origin, 28, models.ADAPTIVE, diagnostics=b)
    assert first == pytest.approx(second)
    assert a == b
    assert all(date.fromisoformat(cut) < origin for cut in a['validation_origins'])
    assert all(math.isfinite(v) and v >= 0 for v in first.values())


def test_selector_records_per_series_horizon_choices_and_optional_fallback(panel, monkeypatch):
    predict = without_ml(monkeypatch)
    info = {}
    values = predict(panel, panel.start + timedelta(days=70), 45, models.ADAPTIVE, diagnostics=info)
    assert len(info['selection']) == len(panel.series) * 3
    assert len(info['unavailable_candidates']) == 2
    assert values
    assert any(row['reason'] != 'limited_validation' for row in info['selection'])
    assert all(sum(row['weights'].values()) == pytest.approx(1) for row in info['selection'])


def test_short_history_and_future_closure_use_baseline(panel, monkeypatch):
    predict = without_ml(monkeypatch)
    origin = panel.start + timedelta(days=28)
    closed = (origin + timedelta(days=1), *panel.series[0])
    panel.closed = frozenset({closed})
    info = {}
    actual = predict(panel, origin, 14, models.ADAPTIVE, diagnostics=info)
    baseline = predict(panel, origin, 14, models.BASELINE)
    assert actual == baseline and actual[closed] == 0
    assert all(row['reason'] == 'limited_validation' for row in info['selection'])


def test_recency_candidate_responds_to_recent_weekday_changes(panel):
    origin = panel.start + timedelta(days=70)
    baseline = models.predict(panel, origin, 7, models.BASELINE)
    recent = models.predict(panel, origin, 7, models.RECENT)
    assert all(recent[k] > baseline[k] for k in baseline)


def test_compiled_poisson_matches_pipeline_on_every_recursive_batch(panel, monkeypatch):
    pytest.importorskip('sklearn')
    import numpy as np
    original = models.poisson_predictor
    batches = []
    def checked(model):
        fast = original(model)
        def compare(values):
            expected = model.predict(values)
            actual = fast(values)
            np.testing.assert_allclose(actual, expected, rtol=1e-12, atol=1e-12)
            batches.append(len(values))
            return actual
        return compare
    monkeypatch.setattr(models, 'poisson_predictor', checked)
    for key in list(panel.observed)[::17]:
        panel.observed.pop(key)
    # Forecast into unseen calendar months while lag values change recursively.
    result = models.predict(panel, panel.start + timedelta(days=56), 50, models.POISSON)
    assert result and len(batches) == 50


def test_scoped_prediction_cache_reuses_longer_prefix_without_refitting(panel, monkeypatch):
    pytest.importorskip('sklearn')
    original = models.poisson_predictor
    fits = []
    def count(model):
        fits.append(1)
        return original(model)
    monkeypatch.setattr(models, 'poisson_predictor', count)
    origin = panel.start + timedelta(days=56)
    cache = {}
    complete = models.predict(panel, origin, 28, models.POISSON, cache=cache)
    prefix = models.predict(panel, origin, 7, models.POISSON, cache=cache)
    assert prefix == {k:v for k,v in complete.items() if k[0] < origin + timedelta(days=7)}
    assert len(fits) == 1
    # A fresh request gets a fresh cache, so changed training data cannot be stale.
    panel.observed[(origin - timedelta(days=1), *panel.series[0])] *= 3
    updated = models.predict(panel, origin, 7, models.POISSON, cache={})
    assert updated != prefix and len(fits) == 2
