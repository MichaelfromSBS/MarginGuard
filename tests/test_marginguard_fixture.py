from pathlib import Path
import shutil

import pytest

from backend.config import ROOT, Settings
from backend.marginguard import db
from backend.marginguard.errors import DomainError
from backend.marginguard.fixture import ingest_fixture
from backend.marginguard.seed import seed_demo

DATA = ROOT / "demo_data/demo_data_v2"


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


def test_schema_two_upgrades_existing_schema_one_without_reset(tmp_path, monkeypatch):
    migrations = tmp_path / "schema_one"
    migrations.mkdir()
    original = db.MIGRATIONS_DIR
    shutil.copyfile(original / "001_initial.sql", migrations / "001_initial.sql")
    database = tmp_path / "upgrade.db"
    monkeypatch.setattr(db, "MIGRATIONS_DIR", migrations)
    assert db.initialize_database(database) == 1
    with db.connect(database) as conn:
        conn.execute("INSERT INTO dishes(id,name) VALUES ('existing','Existing Dish')")
    monkeypatch.setattr(db, "MIGRATIONS_DIR", original)
    assert db.initialize_database(database) == 2
    with db.connect(database) as conn:
        assert conn.execute("SELECT name FROM dishes WHERE id='existing'").fetchone()[0] == "Existing Dish"
        assert conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0] == 2
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
