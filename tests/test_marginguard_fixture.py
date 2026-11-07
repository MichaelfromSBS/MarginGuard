from pathlib import Path
import json
import shutil

import pytest

from backend.config import ROOT, Settings
from backend.marginguard import db
from backend.marginguard.errors import DomainError
from backend.marginguard.fixture import ingest_fixture
from backend.marginguard.seed import seed_demo

DATA = ROOT / "demo_data"


def test_offline_fixture_is_explicit_demo_only_and_uses_normal_validation(tmp_path):
    database = tmp_path / "demo.db"
    seed_demo(database)
    settings = Settings(_env_file=None, database_path=database, upload_directory=tmp_path / "uploads")
    source = DATA / "live_demo/2_invoice_RF-20261107-004.pdf"
    expected = source.with_suffix(".expected.json")
    first = ingest_fixture(settings, source, expected, "invoice")
    assert first["document"]["status"] == "completed"
    assert first["document"]["extraction_method"] == "fixture_expected"
    second = ingest_fixture(settings, source, expected, "invoice")
    assert second["duplicate"] is True
    assert first["document"]["id"] == second["document"]["id"]
    bad_source = DATA / "edge_cases/E4_needs_review_APC-20261107-01.pdf"
    bad = ingest_fixture(settings, bad_source, bad_source.with_suffix(".expected.json"), "invoice")
    assert bad["document"]["status"] == "needs_review"
    with db.connect(database) as conn:
        assert conn.execute("SELECT COUNT(*) FROM invoices").fetchone()[0] == 3
        assert conn.execute("SELECT COUNT(*) FROM alerts").fetchone()[0] == 0


def test_fixture_cannot_approve_expected_json_into_non_demo_restaurant(tmp_path):
    database = tmp_path / "real.db"
    seed_demo(database)
    with db.connect(database) as conn:
        conn.execute("UPDATE restaurant SET is_demo=0")
    settings = Settings(_env_file=None, database_path=database, upload_directory=tmp_path / "uploads")
    source = DATA / "live_demo/2_invoice_RF-20261107-004.pdf"
    with pytest.raises(DomainError) as failure:
        ingest_fixture(settings, source, source.with_suffix(".expected.json"), "invoice")
    assert failure.value.code == "fixture_mode_forbidden"
    assert not settings.upload_directory.exists()


@pytest.mark.parametrize("old_version", [1, 2, 3, 4])
def test_current_schema_upgrades_previous_versions_without_reset(tmp_path, monkeypatch, old_version):
    migrations = tmp_path / "previous_schema"
    migrations.mkdir()
    original = db.MIGRATIONS_DIR
    for source in sorted(original.glob("*.sql"))[:old_version]:
        shutil.copyfile(source, migrations / source.name)
    database = tmp_path / "upgrade.db"
    monkeypatch.setattr(db, "MIGRATIONS_DIR", migrations)
    assert db.initialize_database(database) == old_version
    with db.connect(database) as conn:
        conn.execute("INSERT INTO dishes(id,name) VALUES ('existing','Existing Dish')")
    monkeypatch.setattr(db, "MIGRATIONS_DIR", original)
    assert db.initialize_database(database) == db.SCHEMA_VERSION
    with db.connect(database) as conn:
        assert conn.execute("SELECT name FROM dishes WHERE id='existing'").fetchone()[0] == "Existing Dish"
        assert conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0] == db.SCHEMA_VERSION
        assert conn.execute("SELECT COUNT(*) FROM forecast_snapshots").fetchone()[0] == 0
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_policy_upgrade_archives_legacy_notifications_before_the_api_serves_them(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from backend.main import create_app

    migrations = tmp_path / "schema_four"
    migrations.mkdir()
    original = db.MIGRATIONS_DIR
    for source in sorted(original.glob("*.sql"))[:4]:
        shutil.copyfile(source, migrations / source.name)
    database = tmp_path / "legacy-alerts.db"
    monkeypatch.setattr(db, "MIGRATIONS_DIR", migrations)
    assert db.initialize_database(database) == 4
    evidence = json.dumps([{"kind": "document", "record_id": "original_source"}])
    with db.connect(database) as conn:
        for kind in ["ingredient_price_spike", "projected_cost_increase", "data_quality", "unusual_sales"]:
            conn.execute("""INSERT INTO alerts(id,event_key,type,severity,status,title,message,evidence_json,created_at,updated_at)
                VALUES (?,? ,?,'warning','new','Original finding','Original measured facts',?,'2026-11-07T00:00:00+00:00','2026-11-07T00:00:00+00:00')""",
                (kind, "legacy:" + kind, kind, evidence))
    monkeypatch.setattr(db, "MIGRATIONS_DIR", original)
    with TestClient(create_app(Settings(_env_file=None, database_path=database))) as client:
        assert client.get("/api/alerts?status=new").json()["total"] == 0
        archive = client.get("/api/alerts?status=resolved").json()
        assert archive["total"] == 4
        with db.connect(database) as conn:
            conn.execute("""INSERT INTO alerts(id,event_key,type,severity,status,title,message,evidence_json,created_at,updated_at,calculation_version)
                VALUES ('current','current','projected_cost_increase','warning','new','Current combined alert','New measured facts',?,
                        '2026-11-07T01:00:00+00:00','2026-11-07T01:00:00+00:00','detectors_v2')""", (evidence,))
        assert client.get("/api/alerts?limit=1").json()["items"][0]["id"] == "current"
    with db.connect(database) as conn:
        assert all(row[0] == evidence and row[1] == "Original measured facts" for row in conn.execute("SELECT evidence_json,message FROM alerts WHERE calculation_version='detectors_v1'"))
