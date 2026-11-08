"""Checkpoint 3 numeric, coverage, versioning and leakage acceptance tests."""
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import json
import shutil

from fastapi.testclient import TestClient
import pytest

from backend.config import ROOT, Settings
from backend.main import create_app
from backend.marginguard import analytics, forecasting
from backend.marginguard.db import connect
from backend.marginguard.fixture import ingest_fixture
from backend.marginguard.import_demo import import_demo
from backend.marginguard.schemas import ForecastRequest, ForecastResponse, SalesSummary

DAY = date(2026, 11, 7)
DATA = ROOT / "demo_data"


@pytest.fixture(scope="module")
def baseline(tmp_path_factory):
    path = tmp_path_factory.mktemp("analytics-baseline") / "demo.db"
    import_demo(path)
    return path


@pytest.fixture
def ledger(tmp_path, baseline):
    path = tmp_path / "business.db"
    shutil.copy2(baseline, path)
    return path


@pytest.fixture
def client(ledger, tmp_path):
    settings = Settings(_env_file=None, database_path=ledger, upload_directory=tmp_path / "uploads")
    with TestClient(create_app(settings)) as c:
        yield c


def recalculate(client, **policy):
    response = client.post("/api/forecasts/recalculate", json={"as_of": DAY.isoformat(), "method": "weekday_average_v1", **policy})
    assert response.status_code == 200, response.text
    ForecastResponse.model_validate(response.json())
    return response.json()


def metrics(result):
    return {m["id"]: m["value"] for m in result["metrics"]}


def fixture(ledger, relative="live_demo/2_invoice_RF-20261107-004", kind="invoice"):
    return ingest_fixture(Settings(_env_file=None, database_path=ledger, upload_directory=ledger.parent / "uploads"),
                          DATA / (relative + ".pdf"), DATA / (relative + ".expected.json"), kind)


def test_observed_sales_reconcile_to_receipts_and_breakdowns(client, ledger):
    result = client.get("/api/sales?start=2026-10-31&end=2026-11-06&as_of=2026-11-07").json()
    SalesSummary.model_validate(result)
    assert result["orders"] == 332
    assert result["net_revenue"] == "7400.00"
    assert result["average_order_revenue"] == "22.29"
    assert result["coverage"]["status"] == "complete"
    for dimension in ["by_day", "by_dish", "by_channel"]:
        assert sum(Decimal(r["net_revenue"]) for r in result[dimension]) == Decimal("7400.00")
        assert sum(Decimal(r["units"]) for r in result[dimension]) == Decimal(result["units"])
    assert sum(r["orders"] for r in result["by_day"]) == 332
    assert result["evidence_truncated"] and len(result["evidence"]) == 20
    with connect(ledger) as conn:
        for ref in result["evidence"]:
            row = conn.execute("SELECT * FROM receipt_items WHERE id=?", (ref["record_id"],)).fetchone()
            assert row["source_text"] == ref["quote"]
    filtered = client.get("/api/sales?start=2026-10-31&end=2026-11-06&dish_id=classic_burger&channel_id=delivery&as_of=2026-11-07").json()
    assert len(filtered["by_dish"]) == len(filtered["by_channel"]) == 1
    assert filtered["orders"] < 332


def test_costs_use_current_effective_prices_and_evidence(client, ledger):
    before = client.get("/api/dishes/classic_burger/cost?as_of=2026-11-07").json()
    assert before["ingredient_cost"] == "3.60"
    assert fixture(ledger)["document"]["status"] == "completed"
    result = client.get("/api/dishes/classic_burger/cost?as_of=2026-11-07").json()
    assert result["ingredient_cost"] == "3.96"
    beef = next(r for r in result["ingredients"] if r["ingredient_id"] == "beef")
    assert beef["quantity"] == "0.5" and beef["unit_cost"] == "4.72"
    assert beef["evidence"]["kind"] == "invoice_line"
    delivery = next(c for c in result["channels"] if c["channel_id"] == "delivery")
    assert delivery["contribution"] == "3.84" and delivery["contribution_margin_pct"] == "32"
    assert client.get("/api/dishes/classic_burger/cost?as_of=2026-11-06").json()["ingredient_cost"] == "3.60"
    assert fixture(ledger, "edge_cases/E5_late_arrival_RF-20261030-002")["document"]["status"] == "completed"
    assert client.get("/api/dishes/classic_burger/cost?as_of=2026-11-07").json()["ingredient_cost"] == "3.96"


def test_forecast_matches_independent_fixture_expectations_and_reconciles(client):
    result = recalculate(client)
    assert result["status"] == "ready"
    assert result["horizon"] == {"start": "2026-12-01", "end": "2026-12-31"}
    assert result["training_period"] == {"start": "2026-09-12", "end": "2026-11-06"}
    assert result["training_coverage"]["complete"] == 110
    assert result["training_coverage"]["unknown"] == 2
    values = metrics(result)
    assert values["forecast.revenue"] == "31286.93"
    assert values["forecast.ingredient_cost"] == "9413.63"
    assert len(result["daily"]) == 31 * 6
    assert all(r["units"] == "0" and not r["is_open"] for r in result["daily"] if r["date"] == "2026-12-25")
    for field, metric in [("units", "forecast.units"), ("revenue", "forecast.revenue"), ("ingredient_cost", "forecast.ingredient_cost")]:
        assert sum(Decimal(r[field]) for r in result["series"]) == Decimal(values[metric])
    assert sum(Decimal(r["cost"]) for r in result["ingredients"]) == Decimal(values["forecast.ingredient_cost"])
    for series in result["series"]:
        daily = [r for r in result["daily"] if r["dish_id"] == series["dish_id"] and r["channel_id"] == series["channel_id"]]
        assert sum(Decimal(r["units"]) for r in daily) == Decimal(series["units"])
        assert all("2026-10-14" not in w["sample_dates"] and all(d < "2026-11-07" for d in w["sample_dates"]) for w in series["weekday_estimates"])
    assert [s["volume_multiplier"] for s in result["scenarios"]] == ["0.85", "1", "1.15"]
    assert result["evaluation"]["status"] == "ready" and result["evaluation"]["observations"] == 42


def test_invoice_reprices_same_demand_and_invalidates_saved_snapshot(client, ledger):
    before = recalculate(client)
    assert recalculate(client)["id"] == before["id"]
    fixture(ledger)
    stale = client.get("/api/forecasts/" + before["id"]).json()
    assert stale["status"] == "pending"
    assert metrics(stale)["forecast.ingredient_cost"] == "9413.63"
    assert client.get("/api/dashboard?as_of=2026-11-07").json()["forecast"]["status"] == "pending"
    after = recalculate(client)
    assert after["id"] != before["id"] and after["status"] == "ready"
    assert metrics(after)["forecast.revenue"] == metrics(before)["forecast.revenue"]
    assert metrics(after)["forecast.units"] == metrics(before)["forecast.units"]
    assert metrics(after)["forecast.ingredient_cost"] == "10143.80"
    assert Decimal(metrics(after)["forecast.ingredient_cost"]) - Decimal(metrics(before)["forecast.ingredient_cost"]) == Decimal("730.17")
    assert len(client.get("/api/forecasts?limit=1").json()["items"]) == 1
    assert client.get("/api/forecasts").json()["total"] == 2
    with connect(ledger) as conn:
        assert conn.execute("SELECT COUNT(*) FROM forecast_values").fetchone()[0] == 12
        original = conn.execute("SELECT response_json FROM forecast_snapshots WHERE run_id=?", (before["id"],)).fetchone()[0]
        assert json.loads(original)["status"] == "ready"  # Calculation payload is immutable.


def test_new_partial_day_updates_actuals_without_inventing_a_forecast_training_day(client, ledger):
    before = recalculate(client)
    assert fixture(ledger, "live_demo/1_receipt_TB-20261107-001", "receipt")["document"]["status"] == "completed"
    observed = client.get("/api/sales?start=2026-11-07&end=2026-11-07&as_of=2026-11-07").json()
    assert observed["orders"] == 1 and observed["net_revenue"] == "37.00" and observed["units"] == "3"
    assert observed["coverage"]["status"] == "partial"
    after = recalculate(client)
    assert metrics(after) == metrics(before)
    assert after["source_data_version"] == before["source_data_version"] + 1
    dashboard = client.get("/api/dashboard?start=2026-11-07&end=2026-11-07&as_of=2026-11-07").json()
    assert dashboard["sales"]["net_revenue"] == "37.00"
    assert dashboard["forecast"]["id"] == after["id"]


@pytest.mark.parametrize("hour,minute,expected_start,expected_end", [
    (4, 59, "2026-11-01", "2026-11-07"),
    (5, 1, "2026-11-02", "2026-11-08"),
])
def test_live_default_window_rolls_at_restaurant_midnight_not_utc(client, monkeypatch, hour, minute, expected_start, expected_end):
    instant = datetime(2026, 11, 8, hour, minute, tzinfo=timezone.utc)
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return instant.astimezone(tz)
    monkeypatch.setattr(analytics, "datetime", Clock)
    for path in ["/api/sales", "/api/dashboard"]:
        data = client.get(path).json()
        sales = data["sales"] if path.endswith("dashboard") else data
        assert sales["period"] == {"start": expected_start, "end": expected_end}


def test_confirmed_zero_is_distinct_from_missing_and_coverage_changes_are_audited(client, ledger):
    before = recalculate(client)
    unknown = client.get("/api/sales?start=2026-10-14&end=2026-10-14&as_of=2026-11-07").json()
    assert unknown["net_revenue"] == "0.00" and unknown["coverage"]["status"] == "unknown"
    with connect(ledger) as conn:
        version = conn.execute("SELECT data_version FROM restaurant").fetchone()[0]
    body = {"date": "2026-10-14", "channel_id": "in_store"}
    assert client.post("/api/coverage/complete", json=body).status_code == 200
    assert client.post("/api/coverage/complete", json=body).status_code == 200
    with connect(ledger) as conn:
        assert conn.execute("SELECT data_version FROM restaurant").fetchone()[0] == version + 1
        assert conn.execute("SELECT COUNT(*) FROM coverage_events").fetchone()[0] == 1
    assert client.get("/api/forecasts/" + before["id"]).json()["status"] == "pending"
    after = recalculate(client)
    assert Decimal(metrics(after)["forecast.units"]) < Decimal(metrics(before)["forecast.units"])
    classic = next(s for s in after["series"] if s["dish_id"] == "classic_burger" and s["channel_id"] == "in_store")
    assert "2026-10-14" in classic["weekday_estimates"][2]["sample_dates"]


def test_insufficient_series_does_not_publish_partial_restaurant_totals(client, ledger):
    with connect(ledger) as conn:
        conn.execute("UPDATE daily_coverage SET status='partial' WHERE channel_id='delivery' AND date<'2026-11-07'")
    result = recalculate(client)
    assert result["status"] == "insufficient_history"
    assert all(m["value"] is None for m in result["metrics"])
    assert result["ingredients"] == result["scenarios"] == []
    assert all(s["units"] is None for s in result["series"] if s["channel_id"] == "delivery")
    assert all(s["units"] is not None for s in result["series"] if s["channel_id"] == "in_store")


def test_at_least_four_observations_required_even_if_other_weekdays_are_complete(client, ledger):
    with connect(ledger) as conn:
        rows = conn.execute("SELECT date FROM daily_coverage WHERE channel_id='delivery' AND status='complete' ORDER BY date").fetchall()
        mondays = [r[0] for r in rows if date.fromisoformat(r[0]).weekday() == 0]
        for day in mondays[3:]:
            conn.execute("UPDATE daily_coverage SET status='unknown' WHERE date=? AND channel_id='delivery'", (day,))
    result = recalculate(client)
    assert result["status"] == "insufficient_history"
    assert all(s["weekday_estimates"][0]["mean_units"] is None for s in result["series"] if s["channel_id"] == "delivery")


def test_future_prices_ignored_weight_conversion_and_missing_inputs(client, ledger):
    with connect(ledger) as conn:
        conn.execute("UPDATE recipe_items SET quantity='8',unit='oz' WHERE ingredient_id='beef'")
        conn.execute("INSERT INTO menu_prices VALUES ('future_menu','classic_burger','in_store','99','2026-11-08')")
        conn.execute("""UPDATE ingredient_prices SET effective_date='2026-11-08',unit_cost='99'
                        WHERE id=(SELECT id FROM ingredient_prices WHERE ingredient_id='beef' ORDER BY effective_date DESC LIMIT 1)""")
    result = client.get("/api/dishes/classic_burger/cost?as_of=2026-11-07").json()
    assert result["ingredient_cost"] == "3.60"
    assert next(c for c in result["channels"] if c["channel_id"] == "in_store")["menu_price"] == "12.00"
    with connect(ledger) as conn:
        conn.execute("DELETE FROM ingredient_prices WHERE ingredient_id='beef'")
    result = recalculate(client)
    assert result["status"] == "insufficient_history"
    assert all(m["value"] is None for m in result["metrics"])
    assert any("No compatible approved price" in issue for issue in result["limitations"])


def test_incompatible_recipe_units_cannot_be_priced_as_zero(client, ledger):
    with connect(ledger) as conn:
        conn.execute("UPDATE recipe_items SET unit='each' WHERE ingredient_id='beef'")
    result = client.get("/api/dishes/classic_burger/cost?as_of=2026-11-07").json()
    assert result["ingredient_cost"] is None
    assert any("Incompatible" in issue for issue in result["limitations"])


def test_holdout_evaluation_has_no_training_leakage(ledger):
    # Turn every held-out line into a very large unit observation. Independently
    # reconstruct weekday means only from pre-holdout complete days.
    with connect(ledger) as conn:
        conn.execute("UPDATE receipt_items SET quantity='100' WHERE receipt_id IN (SELECT id FROM receipts WHERE local_date>='2026-10-31')")
        rows = conn.execute("SELECT r.local_date,r.channel_id,i.dish_id,i.quantity FROM receipt_items i JOIN receipts r ON r.id=i.receipt_id").fetchall()
        complete = {(r[0], r[1]) for r in conn.execute("SELECT date,channel_id FROM daily_coverage WHERE status='complete'")}
        daily = defaultdict(lambda: Decimal(0))
        for r in rows:
            daily[(r["local_date"], r["dish_id"], r["channel_id"])] += Decimal(r["quantity"])
        expected, naive = [], []
        dishes = [dict(r) for r in conn.execute("SELECT * FROM dishes ORDER BY id")]
        channels = [dict(r) for r in conn.execute("SELECT * FROM channels ORDER BY id")]
        for dish in dishes:
            for channel in channels:
                for offset in range(7):
                    day = date(2026, 10, 31) + timedelta(days=offset)
                    sample = [d for d, c in complete if c == channel["id"] and date(2026, 9, 5) <= date.fromisoformat(d) < date(2026, 10, 31) and date.fromisoformat(d).weekday() == day.weekday()]
                    mean = sum((daily[(d, dish["id"], channel["id"])] for d in sample), Decimal(0)) / len(sample)
                    actual = daily[(day.isoformat(), dish["id"], channel["id"])]
                    expected.append(abs(actual - mean))
                    naive.append(abs(actual - daily[((day - timedelta(days=7)).isoformat(), dish["id"], channel["id"])]))
        result = forecasting.evaluate(conn, DAY, ForecastRequest(), dishes, channels)
        assert result["observations"] == 42
        assert abs(Decimal(result["weekday_average_mae"]) - sum(expected) / 42) < Decimal("0.0000001")
        assert abs(Decimal(result["seasonal_naive_mae"]) - sum(naive) / 42) < Decimal("0.0000001")


@pytest.mark.parametrize("policy", [{"history_weeks": 3}, {"min_observations": 3}, {"min_observations": 9}, {"sensitivity_pct": "101"}, {"sensitivity_pct": -1}])
def test_invalid_forecast_policy_is_rejected_without_persistence(client, policy):
    assert client.post("/api/forecasts/recalculate", json={"as_of": "2026-11-07", **policy}).status_code == 422
    assert client.get("/api/forecasts").json()["total"] == 0


def test_date_validation_empty_resources_and_calendar_year_boundary(client):
    assert client.get("/api/sales?start=2026-11-07&end=2026-11-06").status_code == 422
    assert client.get("/api/sales?start=2020-01-01&end=2026-11-06").status_code == 422
    assert client.get("/api/sales?end=2026-11-08&as_of=2026-11-07").status_code == 422
    assert client.get("/api/sales?dish_id=missing").status_code == 404
    assert client.get("/api/dishes/missing/cost").status_code == 404
    assert client.get("/api/forecasts/missing").status_code == 404
    result = recalculate(client, as_of="2026-12-31")
    assert result["horizon"] == {"start": "2027-01-01", "end": "2027-01-31"}
    assert result["status"] == "insufficient_history"


def test_coverage_cannot_close_sold_days_or_complete_unfinished_days(client, monkeypatch):
    monkeypatch.setattr(analytics, "local_today", lambda owner: DAY)
    for body, code in [
        ({"date": "2026-11-07", "channel_id": "in_store"}, "day_not_finished"),
        ({"date": "2026-11-08", "channel_id": "delivery"}, "day_not_finished"),
        ({"date": "2026-11-06", "channel_id": "in_store", "status": "closed"}, "closed_day_has_sales"),
        ({"date": "2026-09-01", "channel_id": "in_store", "status": "closed"}, None),
    ]:
        result = client.post("/api/coverage/complete", json=body)
        assert result.status_code == (409 if code else 200)
        if code:
            assert result.json()["error"]["code"] == code


def test_all_closed_horizon_is_zero_not_insufficient_demand(client, ledger):
    with connect(ledger) as conn:
        conn.execute("UPDATE restaurant_calendar SET is_open=0 WHERE date BETWEEN '2026-12-01' AND '2026-12-31'")
        conn.execute("UPDATE daily_coverage SET status='unknown'")
    result = recalculate(client)
    assert result["status"] == "ready"
    assert all(Decimal(v) == 0 for v in metrics(result).values())


def test_future_closure_and_missing_coverage_are_explicit(client):
    result = client.post("/api/coverage/complete", json={"date": "2026-12-01", "channel_id": "delivery", "status": "closed"})
    assert result.status_code == 200
    forecast = recalculate(client)
    assert all(r["units"] == "0" for r in forecast["daily"] if r["date"] == "2026-12-01" and r["channel_id"] == "delivery")
    empty = client.get("/api/sales?start=2026-09-01&end=2026-09-01&as_of=2026-11-07").json()
    assert empty["orders"] == 0 and empty["average_order_revenue"] is None and empty["coverage"]["unknown"] == 2
