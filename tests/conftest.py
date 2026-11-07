"""Every test receives an isolated application database, never the developer's ledger."""
import pytest


@pytest.fixture(autouse=True)
def isolated_database(tmp_path, monkeypatch):
    monkeypatch.setenv("MARGINGUARD_DATABASE_PATH", str(tmp_path / "app.db"))
