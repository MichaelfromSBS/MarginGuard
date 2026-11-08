"""Live model serving and read-only cost/price/demand scenario acceptance tests."""
from datetime import date
from decimal import Decimal
import shutil

from fastapi.testclient import TestClient
import pytest

from backend.config import ROOT, Settings
from backend.main import create_app
from backend.marginguard import analytics, forecasting
from backend.marginguard.db import connect
from backend.marginguard.fixture import ingest_fixture
from backend.marginguard.import_demo import import_demo
from backend.marginguard.schemas import ForecastRequest, PricingScenarioResponse

DAY = date(2026, 11, 7)

@pytest.fixture(scope='module')
def source(tmp_path_factory):
    path = tmp_path_factory.mktemp('pricing-source') / 'demo.db'
    import_demo(path)
    return path

@pytest.fixture
def ledger(tmp_path, source):
    path = tmp_path / 'ledger.db'
    shutil.copy2(source, path)
    return path

@pytest.fixture
def client(ledger, monkeypatch):
    monkeypatch.setattr(analytics, 'local_today', lambda owner: DAY)
    with TestClient(create_app(Settings(_env_file=None, database_path=ledger))) as client:
        yield client

def forecast(client, method='weekday_average_v1'):
    r = client.post('/api/forecasts/recalculate', json={'as_of': DAY.isoformat(), 'method': method})
    assert r.status_code == 200, r.text
    assert r.json()['status'] == 'ready'
    return r.json()

def scenario(client, snapshot, **policy):
    r = client.post(f"/api/forecasts/{snapshot['id']}/pricing-scenario", json=policy)
    assert r.status_code == 200, r.text
    PricingScenarioResponse.model_validate(r.json())
    return r.json()

def classic(result):
    return next(s for s in result['series'] if s['dish_id'] == 'classic_burger' and s['channel_id'] == 'in_store')

@pytest.mark.parametrize('method', ['regularized_poisson_v1', 'poisson_gradient_boosting_v1', 'recency_weekday_v1', 'adaptive_ensemble_v1'])
def test_live_ml_models_serve_cache_and_preserve_policy(client, ledger, method):
    pytest.importorskip('sklearn')
    snapshot = forecast(client, method)
    assert snapshot['method'] == method
    assert snapshot['model_metadata']['elasticity_fitted'] is False
    assert snapshot['evaluation']['selected_method'] == method
    assert snapshot['evaluation']['selected_method_mae'] is not None
    if method == 'adaptive_ensemble_v1':
        decisions = snapshot['model_metadata']['adaptive']['selection']
        assert len(decisions) == 18
        assert all(sum(d['weights'].values()) == pytest.approx(1) for d in decisions)
    assert len(snapshot['daily']) == 31 * 6
    assert all(Decimal(row['units']) >= 0 for row in snapshot['daily'])
    assert client.post('/api/forecasts/recalculate', json={'as_of': DAY.isoformat()}).json()['id'] == snapshot['id']
    with connect(ledger) as conn:
        assert forecasting.default_request(conn, DAY).method == method
    for metric in ['revenue', 'ingredient_cost']:
        total = next(m['value'] for m in snapshot['metrics'] if m['id'] == f'forecast.{metric}')
        assert sum(Decimal(r[metric]) for r in snapshot['series']) == Decimal(total)

@pytest.mark.parametrize('new_cost, direction', [('4.72', -1), ('3.28', 1)])
def test_cost_price_demand_chain_both_directions_and_reconciliation(client, new_cost, direction):
    baseline = forecast(client)
    result = scenario(client, baseline, reference_date=DAY.isoformat(), ingredient_prices=[{'ingredient_id': 'beef', 'unit_cost': new_cost}])
    row = classic(result)
    assert (Decimal(row['units']) - Decimal(row['baseline_units'])) * direction > 0
    assert (Decimal(row['scenario_menu_price']) - Decimal(row['current_menu_price'])) * direction < 0
    assert row['scenario_unit_cost'] == ('3.96' if direction < 0 else '3.24')
    assert result['elasticity_source'] == 'owner_assumption'
    assert any('no usable' in l for l in result['limitations'])
    for metric in ['revenue', 'ingredient_cost', 'units']:
        assert sum(Decimal(r[metric]) for r in result['series']) == Decimal(result[metric])
    assert sum(Decimal(i['cost']) for i in result['ingredients']) == Decimal(result['ingredient_cost'])
    beef = next(i for i in result['ingredients'] if i['ingredient_id'] == 'beef')
    assert beef['price_source'] == 'owner_assumption'
    veggie = next(s for s in result['series'] if s['dish_id'] == 'veggie_burger')
    assert veggie['units'] == veggie['baseline_units']


def test_no_pass_through_means_no_demand_response_and_no_writes(client, ledger):
    baseline = forecast(client)
    with connect(ledger) as conn:
        before = list(conn.iterdump())
    result = scenario(client, baseline, cost_pass_through_pct='0', ingredient_prices=[{'ingredient_id': 'beef', 'unit_cost': '4.72'}])
    assert all(s['baseline_units'] == s['units'] and s['current_menu_price'] == s['scenario_menu_price'] for s in result['series'])
    assert result['fixed_demand_ingredient_cost'] == result['ingredient_cost']
    with connect(ledger) as conn:
        assert list(conn.iterdump()) == before


def test_zero_elasticity_and_manual_menu_override(client):
    baseline = forecast(client)
    result = scenario(client, baseline, price_elasticity='0', menu_prices=[{'dish_id': 'classic_burger', 'channel_id': 'in_store', 'price': '13.20'}])
    row = classic(result)
    assert row['units'] == row['baseline_units'] and row['scenario_menu_price'] == '13.20'
    result = scenario(client, baseline, menu_prices=[{'dish_id': 'classic_burger', 'channel_id': 'in_store', 'price': '13.20'}])
    assert Decimal(classic(result)['demand_multiplier']) == Decimal('0.90909091')


def test_latest_invoice_automatically_supplies_scenario_price_change(client, ledger):
    settings = Settings(_env_file=None, database_path=ledger, upload_directory=ledger.parent / 'uploads')
    base = ROOT / 'demo_data/live_demo/2_invoice_RF-20261107-004'
    ingest_fixture(settings, base.with_suffix('.pdf'), base.with_suffix('.expected.json'), 'invoice')
    result = scenario(client, forecast(client))
    row = classic(result)
    assert row['reference_unit_cost'] == '3.65' and row['current_unit_cost'] == '3.96'
    assert row['scenario_menu_price'] == '12.31'
    assert Decimal(row['units']) < Decimal(row['baseline_units'])

@pytest.mark.parametrize('policy', [
    {'price_elasticity': '1'}, {'price_elasticity': '-5.1'}, {'cost_pass_through_pct': '101'},
    {'reference_date': '2026-11-08'}, {'reference_date': '2026-01-01'},
    {'ingredient_prices': [{'ingredient_id': 'unknown', 'unit_cost': '2'}]},
    {'ingredient_prices': [{'ingredient_id': 'beef', 'unit_cost': '2'}, {'ingredient_id': 'beef', 'unit_cost': '3'}]},
    {'menu_prices': [{'dish_id': 'classic_burger', 'channel_id': 'in_store', 'price': '0'}]},
    {'menu_prices': [{'dish_id': 'classic_burger', 'channel_id': 'in_store', 'price': '1000'}]},
])
def test_invalid_scenarios_rejected(client, policy):
    snapshot = forecast(client)
    r = client.post(f"/api/forecasts/{snapshot['id']}/pricing-scenario", json=policy)
    assert r.status_code in (409, 422), r.text


def test_stale_snapshot_cannot_be_used_for_current_scenario(client, ledger):
    snapshot = forecast(client)
    with connect(ledger) as conn:
        conn.execute('UPDATE restaurant SET data_version=data_version+1')
    assert client.post(f"/api/forecasts/{snapshot['id']}/pricing-scenario", json={}).status_code == 409


def test_model_serving_explicit_missing_dependency_error(client, monkeypatch):
    def unavailable(*args, **kwargs):
        raise ValueError('Install requirements-forecasting.lock.txt to run fitted forecasting models.')
    monkeypatch.setattr(forecasting.demand_models, 'predict', unavailable)
    r = client.post('/api/forecasts/recalculate', json={'as_of': DAY.isoformat(), 'method': 'regularized_poisson_v1'})
    assert r.status_code == 503
    assert r.json()['error']['code'] == 'forecast_model_unavailable'


def test_switching_back_to_cached_model_activates_it_in_dashboard_and_worker(client, ledger, tmp_path):
    import asyncio
    from backend.worker import Worker
    pytest.importorskip('sklearn')
    original = forecast(client)
    ml = forecast(client, 'regularized_poisson_v1')
    assert ml['id'] != original['id']
    switched = forecast(client)
    assert switched['id'] == original['id']
    assert client.get('/api/dashboard?as_of=2026-11-07').json()['forecast']['id'] == original['id']
    settings = Settings(_env_file=None, database_path=ledger, inbox_directory=tmp_path/'empty-inbox', alert_ai_explanations=False)
    async def cycle():
        async with Worker(settings) as worker:
            await worker.cycle(DAY)
        async with Worker(settings) as worker:
            await worker.cycle(DAY)
    asyncio.run(cycle())
    with connect(ledger) as conn:
        assert forecasting.default_request(conn, DAY).method == 'weekday_average_v1'
        from backend.marginguard.chat_tools import execute_tool
        before = list(conn.iterdump())
        conn.execute('PRAGMA query_only=ON')
        answer, _ = execute_tool(conn, 'get_month_forecast', {}, DAY)
        assert answer.evidence[0]['record_id'] == original['id']
        assert list(conn.iterdump()) == before
    assert client.get('/api/dashboard?as_of=2026-11-07').json()['forecast']['id'] == original['id']


def test_ml_selected_policy_retained_after_invoice_and_worker_restart(client, ledger, tmp_path):
    import asyncio
    from backend.worker import Worker
    pytest.importorskip('sklearn')
    forecast(client, 'regularized_poisson_v1')
    settings = Settings(_env_file=None, database_path=ledger, upload_directory=tmp_path/'uploads',
        inbox_directory=tmp_path/'empty-inbox', alert_ai_explanations=False)
    base = ROOT / 'demo_data/live_demo/2_invoice_RF-20261107-004'
    ingest_fixture(settings, base.with_suffix('.pdf'), base.with_suffix('.expected.json'), 'invoice')
    async def cycle():
        async with Worker(settings) as worker:
            await worker.cycle(DAY)
    asyncio.run(cycle())
    result = client.get('/api/dashboard?as_of=2026-11-07').json()['forecast']
    assert result['status'] == 'ready' and result['method'] == 'regularized_poisson_v1'
    assert classic(scenario(client, result))['scenario_unit_cost'] == '3.96'


def test_serving_bridges_current_month_and_honors_future_closures(client, ledger, monkeypatch):
    from backend.marginguard import demand_models
    original = demand_models.predict
    origins = []
    def check(panel, origin, horizon, method, **kwargs):
        assert all(k[0] < DAY for k in panel.observed)
        origins.append((origin, horizon))
        return original(panel, origin, horizon, method, **kwargs)
    monkeypatch.setattr(demand_models, 'predict', check)
    with connect(ledger) as conn:
        conn.execute("INSERT INTO restaurant_calendar(date,is_open) VALUES ('2026-12-05',0) ON CONFLICT(date) DO UPDATE SET is_open=0")
        conn.execute("INSERT INTO daily_coverage(date,channel_id,status,updated_at) VALUES ('2026-12-06','delivery','closed','2026-11-07') ON CONFLICT(date,channel_id) DO UPDATE SET status='closed'")
    snapshot = forecast(client, 'regularized_poisson_v1')
    assert (DAY, 55) in origins
    for row in snapshot['daily']:
        if row['date'] == '2026-12-05' or (row['date'] == '2026-12-06' and row['channel_id'] == 'delivery'):
            assert not row['is_open'] and row['units'] == '0'


def test_auto_is_default_for_new_and_legacy_policy_but_explicit_choices_persist(client, ledger):
    assert ForecastRequest().method == 'adaptive_ensemble_v1'
    with connect(ledger) as conn:
        conn.execute("INSERT INTO worker_state(key,value) VALUES ('forecast_selection','{\"method\":\"weekday_average_v1\"}') ON CONFLICT(key) DO UPDATE SET value=excluded.value")
        conn.execute("DELETE FROM worker_state WHERE key='forecast_default_policy'")
        before = list(conn.iterdump())
        assert forecasting.default_request(conn, DAY).method == 'adaptive_ensemble_v1'
        assert list(conn.iterdump()) == before
    response = client.post('/api/forecasts/recalculate', json={'as_of': DAY.isoformat()})
    assert response.status_code == 200, response.text
    assert response.json()['method'] == 'adaptive_ensemble_v1'
    manual = forecast(client, 'weekday_average_v1')
    assert client.post('/api/forecasts/recalculate', json={'as_of': DAY.isoformat()}).json()['id'] == manual['id']


def test_legacy_default_refresh_is_server_owned_and_read_only(client, ledger):
    original = forecast(client, 'weekday_average_v1')
    with connect(ledger) as conn:
        conn.execute("DELETE FROM worker_state WHERE key='forecast_default_policy'")
    with connect(ledger) as conn:
        before = list(conn.iterdump())
    saved = client.get('/api/dashboard?as_of=2026-11-07').json()['forecast']
    assert saved['status'] == 'pending'
    with connect(ledger) as conn:
        assert list(conn.iterdump()) == before
    # The original immutable run remains readable; only the current policy needs refresh.
    assert client.get('/api/forecasts/'+original['id']).json()['status'] == 'ready'
    updated = client.post('/api/forecasts/recalculate', json={'as_of': DAY.isoformat()}).json()
    assert updated['status'] == 'ready' and updated['method'] == 'adaptive_ensemble_v1'
    chosen = forecast(client, 'regularized_poisson_v1')
    assert client.get('/api/dashboard?as_of=2026-11-07').json()['forecast']['id'] == chosen['id']
