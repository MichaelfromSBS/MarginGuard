"""Chronological, per-series adaptive ensembles with a conservative weekday anchor."""
from datetime import timedelta
import math
import statistics

from . import demand_models as models

BUCKETS = ((1, 7), (8, 14), (15, 28))
CANDIDATES = (models.BASELINE, models.RECENT, models.NAIVE, models.POISSON, models.BOOSTED)


def choose_weights(cases, available):
    """Use shared validation cases; shrink small-sample choices toward the baseline."""
    baseline = models.BASELINE
    eligible = [m for m in available if m == baseline or
        sum(m in row['predictions'] for row in cases) >= .9 * len(cases)]
    common = [r for r in cases if all(m in r['predictions'] for m in eligible)]
    scores = {m: statistics.fmean(abs(r['actual'] - r['predictions'][m]) for r in common) for m in eligible} if common else {}
    folds = len({r['origin'] for r in common})
    result = {'weights': {baseline: 1.0}, 'reason': 'limited_validation',
              'observations': len(common), 'folds': folds, 'mae': scores,
              'eligible_observations': len(cases)}
    if len(common) < 14 or folds < 2 or baseline not in scores:
        return result
    ranking = sorted(scores, key=lambda m: (scores[m], m))
    best = ranking[0]
    if scores[best] >= scores[baseline] * .97:
        result['reason'] = 'baseline_competitive'
        return result
    contenders = [m for m in ranking if scores[m] <= scores[baseline] * 1.05][:3]
    # A clear, repeatedly observed winner can be preferred over a broad mixture.
    clear = folds >= 3 and len(common) >= 21 and len(ranking) > 1 and scores[best] < .8 * scores[ranking[1]]
    if clear:
        contenders = [best]
    strength = min(.75, len(common) / (len(common) + 28))
    raw = {m: 1 / (1 + scores[m]) ** 2 for m in contenders}
    total = sum(raw.values())
    weights = {m: strength * value / total for m, value in raw.items()}
    weights[baseline] = weights.get(baseline, 0) + 1 - strength
    result.update(weights=weights, reason='preferred_model' if clear else 'validation_blend')
    return result


def predict(panel, origin, horizon, *, history_weeks=8, minimum=4, diagnostics=None, cache=None):
    """Every choice, including its validation targets, precedes the forecast origin."""
    cache = {} if cache is None else cache
    unavailable = {}
    def run(method, cut, length):
        try:
            return models.predict(panel, cut, length, method, history_weeks=history_weeks, minimum=minimum, cache=cache)
        except (ValueError, ImportError, ArithmeticError, MemoryError) as exc:
            unavailable[method] = type(exc).__name__
            return {}
    forecasts = {m: run(m, origin, horizon) for m in CANDIDATES}
    available = [m for m in CANDIDATES if m == models.BASELINE or forecasts[m]]
    observations = {k: v for k, v in panel.observed.items() if k[0] < origin}
    cases = {(s, bucket): [] for s in panel.series for bucket in BUCKETS}
    origins = []
    for lag in (28, 21, 14, 7):
        cut = origin - timedelta(days=lag)
        if (cut - panel.start).days < 28:
            continue
        length = min(28, lag)
        origins.append(cut.isoformat())
        predictions = {m: run(m, cut, length) for m in available if m not in unavailable}
        for key, actual in observations.items():
            lead = (key[0] - cut).days + 1
            if not 1 <= lead <= length or key not in predictions.get(models.BASELINE, {}):
                continue
            bucket = next(b for b in BUCKETS if b[0] <= lead <= b[1])
            values = {m: p[key] for m, p in predictions.items() if key in p}
            cases[(key[1:], bucket)].append({'actual': actual, 'predictions': values, 'origin': cut.isoformat()})
    choices = {(s, b): choose_weights(rows, available) for (s, b), rows in cases.items()}
    result = {}
    for key, base in forecasts[models.BASELINE].items():
        lead = (key[0] - origin).days + 1
        bucket = next((b for b in BUCKETS if b[0] <= lead <= b[1]), BUCKETS[-1])
        choice = choices[(key[1:], bucket)]
        # Beyond validated leads, gradually reduce model deviations toward baseline.
        decay = min(1.0, 28 / lead)
        mixed = sum(weight * forecasts[m].get(key, base) for m, weight in choice['weights'].items())
        value = base + decay * (mixed - base)
        if not math.isfinite(value) or value < 0:
            value = base
        result[key] = value
    if diagnostics is not None:
        diagnostics.update({
            'strategy': 'adaptive_ensemble_v1', 'validation_origins': origins,
            'validation_horizon_days': 28, 'unavailable_candidates': unavailable,
            'available_candidates': available,
            'selection': [{'dish_id': s[0], 'channel_id': s[1], 'lead_days': list(bucket), **choice}
                          for (s, bucket), choice in choices.items()],
            'assumptions': [
                'Model weights use only completed observations strictly before the prediction origin.',
                'Per-dish/channel, lead-bucket MAE uses common validation cases; candidates need 90% case coverage.',
                'At least two rolling origins and fourteen cases are required; weights shrink toward weekday averages.',
                'Lead times beyond twenty-eight days reuse the longest validated bucket with deviations reduced by 28/lead.',
                'Overlapping validation windows are dependent; these scores select weights and are not unbiased accuracy estimates.',
                'The separately held-out evaluation refits the complete selector before its own forecast origin.'
            ]})
    return result
