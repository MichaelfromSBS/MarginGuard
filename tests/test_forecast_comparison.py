"""Saved forecast attribution must preserve history and reconcile exact money."""
from copy import deepcopy
from datetime import date
from decimal import Decimal
import json

import pytest

from backend.marginguard.db import connect, initialize_database
from backend.marginguard.errors import DomainError
from backend.marginguard.forecast_comparison import compare_forecasts
from backend.marginguard.schemas import ForecastResponse


def snapshot(run_id, quantity="10", price="2", *, version=1, ingredient="beef", recipe="recipe_burger", **changes):
    cost = format((Decimal(quantity) * Decimal(price)).quantize(Decimal("0.01")), ".2f")
    horizon = {"start": "2026-12-01", "end": "2026-12-31"}
    value = {"id": run_id, "status": "ready", "horizon": horizon, "method": "weekday_average_v1",
        "source_data_version": version, "created_at": "2026-11-07T12:00:00+00:00", "as_of": "2026-11-07",
        "metrics": [{"id": "forecast.ingredient_cost", "label": "Projected ingredient consumption cost", "value": cost,
            "unit": "USD", "kind": "projected", "period": horizon, "as_of": "2026-11-07T12:00:00+00:00", "coverage": "complete",
            "source_data_version": version, "evidence": [], "assumptions": []}], "assumptions": [],
        "ingredients": [{"ingredient_id": ingredient, "quantity": quantity, "base_unit": "lb", "unit_cost": price, "cost": cost,
            "evidence": {"kind": "invoice_line", "record_id": "line_" + run_id, "document_id": "doc_" + run_id,
                         "source_page": 1, "quote": "Ground beef price on this supplier invoice."}}],
        "series": [{"dish_id": "classic_burger", "channel_id": "in_store", "status": "ready", "units": quantity,
            "revenue": "120.00", "ingredient_cost": cost, "menu_price": "12", "recipe_version_id": recipe,
            "weekday_estimates": [], "limitations": []}]}
    value.update(changes)
    ForecastResponse.model_validate(value)
    return value


def save(conn, value, *, status="ready", policy=None):
    conn.execute("""INSERT INTO forecast_runs(id,horizon_start,horizon_end,status,method,source_data_version,assumptions_json,created_at)
        VALUES (?,?,?,?,?,?,?,?)""", (value["id"], value["horizon"]["start"], value["horizon"]["end"], status, value["method"],
        value["source_data_version"], json.dumps(policy or {"history_weeks": 8, "min_observations": 4}), value["created_at"]))
    conn.execute("INSERT INTO forecast_snapshots(run_id,cache_key,as_of_date,response_json) VALUES (?,?,?,?)",
                 (value["id"], value["id"], "2026-11-07", json.dumps(value)))


@pytest.fixture
def database(tmp_path):
    path = tmp_path / "comparison.db"
    initialize_database(path)
    return path


def test_decomposes_usage_price_and_interaction_without_double_counting(database):
    with connect(database) as conn:
        save(conn, snapshot("before", "10", "2"))
        save(conn, snapshot("after", "12", "3", version=2))
    with connect(database) as conn:
        conn.execute("PRAGMA query_only=ON")
        conn.execute("BEGIN")
        result = compare_forecasts(conn, "before", "after")
    assert {key: result[key] for key in ["previous_cost", "current_cost", "change", "usage_effect", "price_effect", "interaction_effect", "rounding_residual"]} == {
        "previous_cost": "20.00", "current_cost": "36.00", "change": "16.00", "usage_effect": "4.00",
        "price_effect": "10.00", "interaction_effect": "2.00", "rounding_residual": "0.00"}
    assert result["source_data_version"] == 2
    assert len(result["ingredient_effects"]) == 1
    assert {e["kind"] for e in result["evidence"]} == {"forecast_run", "invoice_line"}
    assert any("dish mix" in limitation for limitation in result["limitations"])


def test_historical_ready_payloads_remain_comparable_after_runs_become_stale(database):
    with connect(database) as conn:
        save(conn, snapshot("before"), status="pending")
        save(conn, snapshot("after", price="2.72", version=2), status="pending")
        conn.execute("INSERT INTO restaurant(id,name,currency,timezone,data_version,is_demo) VALUES ('r','Restaurant','USD','America/New_York',3,1)")
    with connect(database) as conn:
        before = list(conn.iterdump())
        conn.execute("PRAGMA query_only=ON")
        result = compare_forecasts(conn, "before", "after")
        after = list(conn.iterdump())
    assert before == after
    assert result["change"] == result["price_effect"] == "7.20"
    assert result["usage_effect"] == result["interaction_effect"] == "0.00"
    assert any("older ledger version" in limitation for limitation in result["limitations"])


def test_rounding_residual_reconciles_displayed_headline_difference(database):
    with connect(database) as conn:
        save(conn, snapshot("before", "1", "0.0049"))
        save(conn, snapshot("after", "2", "0.0061", version=2))
        result = compare_forecasts(conn, "before", "after")
    assert result["previous_cost"] == "0.00" and result["current_cost"] == "0.01"
    assert result["rounding_residual"] == "0.01"
    assert sum(Decimal(result[k]) for k in ["usage_effect", "price_effect", "interaction_effect", "rounding_residual"]) == Decimal(result["change"])
    row = result["ingredient_effects"][0]
    assert sum(Decimal(row[k]) for k in ["usage_effect", "price_effect", "interaction_effect", "rounding_residual"]) == Decimal(row["change"])


@pytest.mark.parametrize("modification", ["horizon", "method", "recipe", "ingredient", "unit", "series", "policy"])
def test_incompatible_comparison_bases_are_rejected(database, modification):
    old, new = snapshot("before"), snapshot("after", "12", "3", version=2)
    policy = None
    if modification == "horizon":
        new["horizon"] = {"start": "2027-01-01", "end": "2027-01-31"}
        new["metrics"][0]["period"] = new["horizon"]
    elif modification == "method":
        new["method"] = "another_method"
    elif modification == "recipe":
        new["series"][0]["recipe_version_id"] = "recipe_new"
    elif modification == "ingredient":
        new["ingredients"][0]["ingredient_id"] = "chicken"
    elif modification == "unit":
        new["ingredients"][0]["base_unit"] = "oz"
    elif modification == "series":
        new["series"][0]["channel_id"] = "delivery"
    elif modification == "policy":
        policy = {"history_weeks": 4, "min_observations": 4}
    with connect(database) as conn:
        save(conn, old)
        save(conn, new, policy=policy)
        with pytest.raises(DomainError) as error:
            compare_forecasts(conn, "before", "after")
    assert error.value.code == "forecast_comparison_incompatible"


@pytest.mark.parametrize("modification", ["insufficient", "missing_cost", "duplicate_ingredient", "incorrect_total", "metadata", "invalid_json_shape"])
def test_unavailable_or_inconsistent_snapshots_do_not_produce_numbers(database, modification):
    old, new = snapshot("before"), snapshot("after", "12", "3", version=2)
    if modification == "insufficient":
        new["status"] = "insufficient_history"
    elif modification == "missing_cost":
        new["metrics"] = []
    elif modification == "duplicate_ingredient":
        new["ingredients"].append(deepcopy(new["ingredients"][0]))
    elif modification == "incorrect_total":
        new["metrics"][0]["value"] = "999.00"
    with connect(database) as conn:
        save(conn, old)
        save(conn, new)
        if modification == "metadata":
            conn.execute("UPDATE forecast_runs SET source_data_version=9 WHERE id='after'")
        elif modification == "invalid_json_shape":
            conn.execute("UPDATE forecast_snapshots SET response_json='[]' WHERE run_id='after'")
        with pytest.raises(DomainError) as error:
            compare_forecasts(conn, "before", "after")
    assert error.value.code == "forecast_comparison_unavailable"


def test_unknown_ids_and_injection_like_ids_are_bound_lookups(database):
    with connect(database) as conn:
        save(conn, snapshot("before"))
        with pytest.raises(DomainError) as error:
            compare_forecasts(conn, "before", "'; DROP TABLE forecast_runs;--")
        assert error.value.code == "forecast_not_found"
        assert conn.execute("SELECT COUNT(*) FROM forecast_runs").fetchone()[0] == 1


def test_same_snapshot_is_zero_change_and_deduplicates_evidence(database):
    with connect(database) as conn:
        save(conn, snapshot("same"))
        result = compare_forecasts(conn, "same", "same")
    assert all(Decimal(result[key]) == 0 for key in ["change", "usage_effect", "price_effect", "interaction_effect", "rounding_residual"])
    assert result["evidence"] == [{"kind": "forecast_run", "record_id": "same"}]


def test_real_saved_demo_snapshots_explain_beef_price_effect_without_rebuilding_history(database):
    from backend.config import ROOT, Settings
    from backend.marginguard.fixture import ingest_fixture
    from backend.marginguard.forecasting import calculate
    from backend.marginguard.import_demo import import_demo
    from backend.marginguard.schemas import ForecastRequest

    import_demo(database)
    policy = ForecastRequest(as_of=date(2026, 11, 7), method="weekday_average_v1")
    with connect(database) as conn:
        previous = calculate(conn, policy)
    source = ROOT / "demo_data/live_demo/2_invoice_RF-20261107-004.pdf"
    settings = Settings(_env_file=None, database_path=database, upload_directory=database.parent / "uploads")
    assert ingest_fixture(settings, source, source.with_suffix(".expected.json"), "invoice")["document"]["status"] == "completed"
    with connect(database) as conn:
        current = calculate(conn, policy)
    with connect(database) as conn:
        conn.execute("PRAGMA query_only=ON")
        result = compare_forecasts(conn, previous.id, current.id)
    assert result["previous_cost"] == "9413.63" and result["current_cost"] == "10143.80"
    assert result["change"] == result["price_effect"] == "730.17"
    assert result["usage_effect"] == result["interaction_effect"] == result["rounding_residual"] == "0.00"
    assert any(e["kind"] == "invoice_line" for e in result["evidence"])
