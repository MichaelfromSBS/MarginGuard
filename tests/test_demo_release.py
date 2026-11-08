"""Visitor demo isolation and the remaining application's request boundary."""
from datetime import date
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from backend.config import Settings
from backend.main import create_app
from backend.marginguard import analytics
from backend.marginguard.db import connect
from backend.marginguard.seed import seed_demo
from scripts.demo import DEMO_DATE, demo_environment, prepare_database


def test_demo_environment_never_inherits_live_credentials_or_owner_paths(monkeypatch):
    monkeypatch.setenv('OPENROUTER_API_KEY', 'private-test-key')
    monkeypatch.setenv('MARGINGUARD_DATABASE_PATH', 'private-business.db')
    monkeypatch.setenv('CODESPACE_NAME', 'sample-codespace')
    monkeypatch.setenv('GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN', 'app.github.dev')
    env = demo_environment(port=8016)
    assert env['AI_MODE'] == 'mock'
    assert env['OPENROUTER_API_KEY'] == ''
    assert Path(env['MARGINGUARD_DATABASE_PATH']).parent.name == 'visitor-demo'
    assert env['MARGINGUARD_DEMO_AS_OF'] == DEMO_DATE
    assert 'https://sample-codespace-8016.app.github.dev' in env['MARGINGUARD_ALLOWED_ORIGINS']
    import os
    assert os.environ['OPENROUTER_API_KEY'] == 'private-test-key'
    assert os.environ['MARGINGUARD_DATABASE_PATH'] == 'private-business.db'


def test_demo_date_is_request_scoped_and_only_for_fictional_restaurants(tmp_path):
    path = tmp_path / 'demo.db'
    seed_demo(path)
    frozen = Settings(_env_file=None, database_path=path, demo_as_of=date(2026, 11, 7))
    normal = Settings(_env_file=None, database_path=path)
    with TestClient(create_app(frozen)) as demo, TestClient(create_app(normal)) as live:
        assert demo.get('/api/health').json()['demo_as_of'] == '2026-11-07'
        assert demo.get('/api/sales').json()['period']['end'] == '2026-11-07'
        assert live.get('/api/sales').json()['period']['end'] == analytics.local_today({'timezone': 'America/New_York'}).isoformat()
    with connect(path) as conn:
        conn.execute('UPDATE restaurant SET is_demo=0')
    with pytest.raises(ValueError, match='fictional demo restaurant'):
        with TestClient(create_app(frozen)):
            pass
    token = analytics.demo_clock.set(date(2000, 1, 1))
    try:
        assert analytics.local_today({'timezone': 'America/New_York', 'is_demo': False}) != date(2000, 1, 1)
    finally:
        analytics.demo_clock.reset(token)


def test_prepared_demo_has_forecasts_sources_alerts_and_preserves_saved_state(tmp_path):
    settings = Settings(_env_file=None, ai_mode='mock', database_path=tmp_path / 'demo.db',
                        upload_directory=tmp_path / 'uploads', demo_as_of=date.fromisoformat(DEMO_DATE))
    prepare_database(settings)
    with TestClient(create_app(settings)) as client:
        dashboard = client.get('/api/dashboard').json()
        assert dashboard['forecast']['status'] == 'ready'
        assert dashboard['forecast']['method'] == 'adaptive_ensemble_v1'
        assert any(m['id'] == 'sales.net_revenue' and m['value'] is not None for m in dashboard['metrics'])
        alerts = client.get('/api/alerts?status=new').json()['items']
        assert len(alerts) == 1
        assert alerts[0]['type'] == 'projected_cost_increase'
        assert client.post(f"/api/alerts/{alerts[0]['id']}/acknowledge").json()['status'] == 'acknowledged'
        assert client.get('/api/invoices').json()['total'] == 9
        assert client.get('/api/receipts').json()['total'] == 2734
        for ref in alerts[0]['evidence']:
            if not ref.get('document_id'):
                continue
            doc_id = ref['document_id']
            detail = client.get(f'/api/documents/{doc_id}').json()
            if detail['extraction_method'] == 'fixture_history':
                assert detail['source_text']
            else:
                assert client.get(f'/api/documents/{doc_id}/source').status_code == 200
    prepare_database(settings)
    with TestClient(create_app(settings)) as client:
        assert client.get('/api/alerts?status=new').json()['total'] == 0
        assert client.get('/api/alerts?status=acknowledged').json()['total'] == 1
        assert client.get('/api/receipts').json()['total'] == 2734


def test_application_guard_allows_only_local_or_explicit_origins_and_caps_uploads(tmp_path):
    settings = Settings(_env_file=None, database_path=tmp_path / 'app.db',
                        allowed_origins=['https://sample-8000.app.github.dev'])
    with TestClient(create_app(settings)) as client:
        for origin in ['http://127.0.0.1:5173', 'https://sample-8000.app.github.dev']:
            assert client.get('/api/health', headers={'Origin': origin}).status_code == 200
        rejected = client.get('/api/health', headers={'Origin': 'https://untrusted.example'})
        assert rejected.status_code == 403
        assert rejected.json()['error']['code'] == 'origin_not_allowed'
        assert client.post('/api/documents', content=b'', headers={'Content-Length': '5000001'}).status_code == 413
        paths = client.get('/openapi.json').json()['paths']
        assert '/api/run' not in paths and '/api/stream' not in paths
        assert '/api/chat' in paths
