"""Offline demand-model evaluation. Reads the ledger; never changes live forecasts.

python -m backend.marginguard.forecast_benchmark --database data/demo-v2.db --output report.json
Install requirements-forecasting.lock.txt for the optional fitted candidates.
"""
import argparse
from datetime import date, timedelta
import json
import math
from pathlib import Path
import statistics

from . import analytics
from .db import connect

from .demand_models import (BASELINE, NAIVE, BOOSTED, POISSON, METHODS, Panel,
                            load_panel, average, features, predict)


def score(cases):
    if not cases:
        return {"observations": 0, "mae": None, "rmse": None, "wape": None}
    errors = [abs(actual - prediction) for actual, prediction in cases]
    actual_sum = sum(actual for actual, _ in cases)
    return {"observations": len(cases), "mae": round(statistics.fmean(errors), 6),
            "rmse": round(math.sqrt(statistics.fmean(e * e for e in errors)), 6),
            "wape": round(sum(errors) / actual_sum, 6) if actual_sum else None}


def evaluate(panel, *, horizons=(7, 28), initial_days=28, step=7, methods=METHODS):
    if initial_days < 28 or step < 1 or not methods or any(m not in METHODS for m in methods):
        raise ValueError("Use an initial window of at least 28 days and supported methods.")
    report = {"source_data_version": panel.source_data_version, "is_demo": panel.is_demo,
        "data_start": panel.start.isoformat(), "data_end": panel.end.isoformat(), "horizons": [],
        "feature_names": ["dish", "channel", "weekday", "month", "day_of_month", "elapsed_days",
            "lag_1", "lag_7", "lag_14", "lag_28", "mean_7", "mean_28", "same_weekday_mean_4", "known_days_28"],
        "limitations": [
            "Historical simulation uses the currently approved ledger and coverage, not reconstructed ingestion-time snapshots.",
            "Future sales actuals are excluded from both fitting and recursive forecasting.",
            "Only common eligible observations are scored; coverage and skipped counts are reported.",
            "Overlapping fold errors are dependent. Short or fictional histories do not establish real-world forecast accuracy.",
            "This benchmark does not promote a model or modify production forecast snapshots."]}
    for horizon in horizons:
        if not 1 <= horizon <= 62:
            raise ValueError("Evaluation horizons must be between one and 62 days.")
        pooled = {m: [] for m in methods}
        folds = []
        origin = panel.start + timedelta(days=initial_days)
        while origin + timedelta(days=horizon - 1) <= panel.end:
            end = origin + timedelta(days=horizon - 1)
            targets = {k: v for k, v in panel.observed.items() if origin <= k[0] <= end}
            predictions = {m: predict(panel, origin, horizon, m) for m in methods}
            common = set(targets).intersection(*(set(p) for p in predictions.values()))
            measures = {}
            for method in methods:
                cases = [(targets[k], predictions[method][k]) for k in sorted(common)]
                pooled[method].extend(cases)
                measures[method] = score(cases)
            folds.append({"origin": origin.isoformat(), "end": end.isoformat(),
                "eligible_observations": len(targets), "scored_observations": len(common),
                "skipped_observations": len(targets) - len(common), "metrics": measures})
            origin += timedelta(days=step)
        report["horizons"].append({"days": horizon, "folds": folds,
            "metrics": {m: score(pooled[m]) for m in methods},
            "evaluation_status": "limited_history" if len(folds) < 3 else "available",
            "automatic_promotion": False})
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if not args.database.is_file():
        parser.error("Use an existing populated database; no database is created or seeded.")
    if args.database.resolve() == args.output.resolve():
        parser.error("The report cannot overwrite the source database.")
    try:
        with connect(args.database) as conn:
            conn.execute("PRAGMA query_only=ON")
            conn.execute("BEGIN")
            panel = load_panel(conn)
        report = evaluate(panel)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps({"output": str(args.output), "is_demo": panel.is_demo,
        "horizons": [{"days": h["days"], "folds": len(h["folds"]), "metrics": h["metrics"]} for h in report["horizons"]]}))


if __name__ == "__main__":
    main()
