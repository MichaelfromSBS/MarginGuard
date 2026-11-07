"""Read-only owner answers must retain period, evidence and snapshot semantics."""
from datetime import date, timedelta
from decimal import Decimal
import json
import shutil

import pytest
from pydantic import ValidationError

from backend.config import ROOT, Settings
from backend.marginguard import analytics, forecasting
from backend.marginguard.chat_tools import execute_tool
from backend.marginguard.db import connect
from backend.marginguard.errors import DomainError
from backend.marginguard.fixture import ingest_fixture
from backend.marginguard.import_demo import import_demo
from backend.marginguard.schemas import ForecastRequest, Metric

DAY = date(2026, 11, 7)


@pytest.fixture(scope="module")
def baseline(tmp_path_factory):
    path = tmp_path_factory.mktemp("chat-tools-baseline") / "demo.db"
    import_demo(path)
    return path


@pytest.fixture
def ledger(tmp_path, baseline):
    path = tmp_path / "business.db"
    shutil.copy2(baseline, path)
    return path


def run(ledger, name, arguments=None, *, today=DAY):
    with connect(ledger) as conn:
        before = list(conn.iterdump())
        conn.execute("PRAGMA query_only=ON")
        conn.execute("BEGIN")
        result, normalized = execute_tool(conn, name, arguments or {}, today)
        assert conn.in_transaction
        assert before == list(conn.iterdump()), "A chat tool changed the business ledger."
        for value in result.metrics:
            Metric.model_validate(value)
        return result, normalized


def values(result):
    return {m.id: m.value for m in map(Metric.model_validate, result.metrics)}


def save_forecast(ledger, **kwargs):
    with connect(ledger) as conn:
        result = forecasting.calculate(conn, ForecastRequest(as_of=DAY, **kwargs))
    assert result.status == "ready"
    return result


def update_payload(ledger, forecast_id, change):
    with connect(ledger) as conn:
        payload = json.loads(conn.execute("SELECT response_json FROM forecast_snapshots WHERE run_id=?", (forecast_id,)).fetchone()[0])
        change(payload)
        conn.execute("UPDATE forecast_snapshots SET response_json=? WHERE run_id=?", (json.dumps(payload), forecast_id))


def test_rolling_sales_and_calendar_week_are_distinct(ledger):
    rolling, _ = run(ledger, "get_sales_summary")
    assert values(rolling)["sales.net_revenue"] == "7400.00"
    assert values(rolling)["sales.orders"] == "332"
    assert "2026-10-31 through 2026-11-06" in rolling.answer
    week, args = run(ledger, "get_sales_summary", '{"period":"last_week"}')
    assert "2026-10-26 through 2026-11-01" in week.answer
    assert args["period"] == "last_week"
    assert values(week)["sales.net_revenue"] != "7400.00"


def test_dish_and_channel_filter_controls_totals_rankings_and_evidence(ledger):
    args = {"dish_id": "classic_burger", "channel_id": "delivery", "breakdown": "dish"}
    result, _ = run(ledger, "get_sales_summary", args)
    with connect(ledger) as conn:
        expected = analytics.sales_summary(conn, date(2026, 10, 31), date(2026, 11, 6),
                                           dish_id="classic_burger", channel_id="delivery")
        for ref in result.evidence:
            row = conn.execute("SELECT i.dish_id,r.channel_id FROM receipt_items i JOIN receipts r ON r.id=i.receipt_id WHERE i.id=?", (ref["record_id"],)).fetchone()
            assert tuple(row) == ("classic_burger", "delivery")
    assert values(result)["sales.net_revenue"] == expected["net_revenue"]
    assert values(result)["sales.orders"] == str(expected["orders"])
    assert "only that dish" in result.answer
    assert all("veggie" not in m.id for m in map(Metric.model_validate, result.metrics))


def test_last_complete_days_excludes_internal_gap_including_from_evidence(ledger):
    with connect(ledger) as conn:
        conn.execute("UPDATE daily_coverage SET status='partial' WHERE date='2026-11-04'")
    result, _ = run(ledger, "get_sales_summary", {"period": "last_7_complete_days", "breakdown": "day"})
    assert "2026-10-30" in result.answer and "2026-11-04" not in result.answer
    metrics = list(map(Metric.model_validate, result.metrics))
    assert all(m.coverage == "complete" for m in metrics)
    assert all("2026-11-04" not in m.id for m in metrics)
    assert any("only these complete dates" in text for text in metrics[0].assumptions)
    with connect(ledger) as conn:
        expected = sum((Decimal(analytics.sales_summary(conn, DAY - timedelta(days=offset), DAY - timedelta(days=offset))["net_revenue"])
                        for offset in range(1, 9) if offset != 3), Decimal(0))
        assert Decimal(values(result)["sales.net_revenue"]) == expected
        for ref in result.evidence:
            assert conn.execute("SELECT r.local_date FROM receipt_items i JOIN receipts r ON r.id=i.receipt_id WHERE i.id=?", (ref["record_id"],)).fetchone()[0] != "2026-11-04"


def test_unknown_coverage_does_not_claim_zero_business_sales(ledger):
    result, _ = run(ledger, "get_sales_summary", {"period": "custom", "start": "2026-08-01", "end": "2026-08-02"})
    assert values(result)["sales.net_revenue"] == "0.00"
    assert Metric.model_validate(result.metrics[0]).coverage == "unknown"
    assert any("not full-period business sales" in text for text in result.limitations)
    assert not result.evidence


@pytest.mark.parametrize("name,arguments", [
    ("get_sales_summary", {"as_of": "2026-11-08"}),
    ("get_sales_summary", {"period": "custom", "start": "2026-11-01", "end": "2026-11-08"}),
    ("get_ingredient_history", {"ingredient_id": "beef", "end": "2026-11-08"}),
    ("get_dish_cost", {"dish_id": "classic_burger", "as_of": "2026-11-08"}),
])
def test_future_observations_cannot_be_requested(ledger, name, arguments):
    with pytest.raises(DomainError):
        run(ledger, name, arguments)


@pytest.mark.parametrize("arguments", [{"period": "custom"}, {"start": "2026-11-01"},
                                          {"as_of": 1794000000}, {"sql": "DROP TABLE receipts"}])
def test_argument_shapes_are_strict_and_sql_is_not_an_operation(ledger, arguments):
    with pytest.raises(ValidationError):
        run(ledger, "get_sales_summary", arguments)


def test_ingredient_history_respects_as_of_and_same_date_latest_rowid(ledger):
    with connect(ledger) as conn:
        row = dict(conn.execute("SELECT * FROM ingredient_prices WHERE ingredient_id='beef' ORDER BY effective_date DESC LIMIT 1").fetchone())
        fields = list(row)
        line = dict(conn.execute("SELECT * FROM invoice_lines WHERE id=?", (row["invoice_line_id"],)).fetchone())
        line_fields = list(line)
        for price_id, cost, effective in [("tie_a", "4.5", row["effective_date"]), ("tie_b", "4.72", row["effective_date"]), ("future", "99", "2026-11-08")]:
            line["id"] = "line_" + price_id
            conn.execute(f"INSERT INTO invoice_lines({','.join(line_fields)}) VALUES ({','.join('?' for _ in line_fields)})", tuple(line[f] for f in line_fields))
            row.update(id=price_id, unit_cost=cost, effective_date=effective, invoice_line_id=line["id"])
            conn.execute(f"INSERT INTO ingredient_prices({','.join(fields)}) VALUES ({','.join('?' for _ in fields)})", tuple(row[f] for f in fields))
    result, _ = run(ledger, "get_ingredient_history", {"ingredient_id": "beef"})
    assert values(result)["ingredient.first_price"] == "4"
    assert values(result)["ingredient.latest_price"] == "4.72"
    assert Decimal(values(result)["ingredient.change_pct"]) == 18
    assert "$99" not in result.answer
    earlier, _ = run(ledger, "get_ingredient_history", {"ingredient_id": "beef", "as_of": "2026-10-01"})
    assert values(earlier)["ingredient.latest_price"] == "4"


def test_missing_recipe_input_never_becomes_a_zero_cost(ledger):
    with connect(ledger) as conn:
        conn.execute("DELETE FROM ingredient_prices WHERE ingredient_id='beef'")
    result, _ = run(ledger, "get_dish_cost", {"dish_id": "classic_burger", "channel_id": "delivery"})
    assert result.unavailable
    assert values(result)["dish.classic_burger.ingredient_cost"] is None
    assert values(result)["dish.classic_burger.contribution"] is None
    assert "missing" in result.answer


def test_saved_forecast_filter_is_independent_of_metric_order(ledger):
    forecast = save_forecast(ledger)
    update_payload(ledger, forecast.id, lambda payload: payload["metrics"].reverse())
    result, _ = run(ledger, "get_month_forecast", {"dish_id": "classic_burger", "channel_id": "delivery"})
    selected = next(s for s in forecast.series if s.dish_id == "classic_burger" and s.channel_id == "delivery")
    assert values(result) == {"forecast.units": selected.units, "forecast.revenue": selected.revenue,
                              "forecast.ingredient_cost": selected.ingredient_cost}
    assert not result.unavailable
    assert "filtered totals" in result.answer


@pytest.mark.parametrize("staleness", ["version", "pending", "old_date", "missing_series_input", "missing_metric"])
def test_unusable_forecast_does_not_report_old_or_partial_totals(ledger, staleness):
    forecast = save_forecast(ledger)
    with connect(ledger) as conn:
        if staleness == "version":
            conn.execute("UPDATE restaurant SET data_version=data_version+1")
        elif staleness == "pending":
            conn.execute("UPDATE forecast_runs SET status='pending'")
    if staleness == "old_date":
        today = DAY + timedelta(days=1)
    else:
        today = DAY
    if staleness == "missing_series_input":
        update_payload(ledger, forecast.id, lambda p: p["series"][0].update(ingredient_cost=None, status="missing_inputs"))
    if staleness == "missing_metric":
        update_payload(ledger, forecast.id, lambda p: p["metrics"].pop())
    result, _ = run(ledger, "get_month_forecast", {"dish_id": forecast.series[0].dish_id, "channel_id": forecast.series[0].channel_id}, today=today)
    assert result.unavailable and not result.metrics
    assert forecast.id in [ref["record_id"] for ref in result.evidence]


def test_missing_forecast_and_alert_reads_do_not_initialize_or_recalculate(ledger):
    result, _ = run(ledger, "get_month_forecast")
    assert result.unavailable and not result.metrics
    result, _ = run(ledger, "get_alerts", {"status": "all"})
    assert values(result)["alerts.count"] == "0"
    with connect(ledger) as conn:
        assert conn.execute("SELECT COUNT(*) FROM forecast_runs").fetchone()[0] == 0


def test_explicit_historical_comparison_preserves_saved_data_version(ledger):
    previous = save_forecast(ledger)
    source = ROOT / "demo_data/live_demo/2_invoice_RF-20261107-004.pdf"
    settings = Settings(_env_file=None, database_path=ledger, upload_directory=ledger.parent / "uploads")
    assert ingest_fixture(settings, source, source.with_suffix(".expected.json"), "invoice")["document"]["status"] == "completed"
    current = save_forecast(ledger)
    with connect(ledger) as conn:
        conn.execute("UPDATE restaurant SET data_version=data_version+1")
        conn.execute("UPDATE forecast_runs SET status='pending'")
    result, _ = run(ledger, "explain_forecast_change", {"previous_id": previous.id, "current_id": current.id})
    assert values(result)["forecast_change.price_effect"] == "730.17"
    assert all(m.source_data_version == current.source_data_version for m in result.metrics)
    assert any("older ledger version" in text for text in result.limitations)


def test_automatic_comparison_requires_current_ready_snapshot(ledger):
    save_forecast(ledger)
    with connect(ledger) as conn:
        conn.execute("UPDATE forecast_runs SET status='pending'")
    result, _ = run(ledger, "explain_forecast_change")
    assert result.unavailable and not result.metrics


def test_automatic_comparison_does_not_use_a_future_snapshot_as_previous(ledger):
    previous = save_forecast(ledger)
    source = ROOT / "demo_data/live_demo/2_invoice_RF-20261107-004.pdf"
    settings = Settings(_env_file=None, database_path=ledger, upload_directory=ledger.parent / "uploads")
    ingest_fixture(settings, source, source.with_suffix(".expected.json"), "invoice")
    current = save_forecast(ledger)
    with connect(ledger) as conn:
        # A later-saved snapshot can share the horizon and all recipe inputs;
        # it must still never become the implied earlier baseline.
        row = dict(conn.execute("SELECT * FROM forecast_runs WHERE id=?", (current.id,)).fetchone())
        row["id"] = "future"
        fields = list(row)
        conn.execute(f"INSERT INTO forecast_runs({','.join(fields)}) VALUES ({','.join('?' for _ in fields)})", tuple(row[f] for f in fields))
        payload = current.model_dump(mode="json")
        payload.update(id="future", as_of="2026-11-08")
        conn.execute("INSERT INTO forecast_snapshots(run_id,cache_key,as_of_date,response_json) VALUES ('future','future','2026-11-08',?)", (json.dumps(payload),))
    result, _ = run(ledger, "explain_forecast_change")
    assert not result.unavailable
    assert values(result)["forecast_change.price_effect"] == "730.17"
    assert previous.id in result.answer and current.id in result.answer and "future" not in result.answer


def test_alert_filters_return_existing_evidence_without_acknowledging(ledger):
    from backend.marginguard.detectors import record

    with connect(ledger) as conn:
        row = analytics.sales_rows(conn, date(2026, 11, 6), date(2026, 11, 6))[0]
        refs = [analytics.evidence(row)]
        record(conn, "unusual:test1", "unusual_sales", "Unusual sales yesterday", "Observed sales differ from the saved baseline.", {}, refs, "Review receipts.")
        acknowledged = record(conn, "unusual:test2", "unusual_sales", "Earlier unusual sales", "Earlier finding.", {}, refs, "Review receipts.")
        conn.execute("UPDATE alerts SET status='acknowledged' WHERE id=?", (acknowledged,))
    result, _ = run(ledger, "get_alerts", {"type": "unusual_sales"})
    assert values(result)["alerts.count"] == "1"
    assert result.evidence == refs
    assert "Earlier unusual sales" not in result.answer
    all_result, _ = run(ledger, "get_alerts", {"status": "all"})
    assert values(all_result)["alerts.count"] == "2"
    with connect(ledger) as conn:
        assert sorted(r[0] for r in conn.execute("SELECT status FROM alerts")) == ["acknowledged", "new"]


def test_cost_alert_month_filters_forecast_horizon_instead_of_creation_date(ledger):
    from backend.marginguard.detectors import record

    with connect(ledger) as conn:
        for month in ["2026-12", "2027-01"]:
            record(conn, "cost:" + month, "projected_cost_increase", month + " cost increase", month + " supplier-cost finding.",
                   {"horizon": {"start": month + "-01", "end": month + "-31"}}, [], "Review supplier prices.")
        record(conn, "unusual", "unusual_sales", "December unusual sales", "December sales finding.", {}, [], "Review receipts.")
    result, args = run(ledger, "get_alerts", {"month": "2026-12"})
    assert values(result)["alerts.count"] == "1"
    assert "2026-12 supplier-cost finding" in result.answer
    assert "2027-01" not in result.answer and "December sales finding" not in result.answer
    assert args["month"] == "2026-12"
    with pytest.raises(DomainError) as error:
        run(ledger, "get_alerts", {"month": "2026-12", "type": "unusual_sales"})
    assert error.value.code == "invalid_chat_filter"
    with pytest.raises(ValidationError):
        run(ledger, "get_alerts", {"month": "2026-13"})
