from decimal import Decimal
import hashlib
import json
import shutil
import sqlite3

import pytest

from backend.marginguard import db
from backend.marginguard.seed import main, seed_demo


def test_schema_initializes_without_business_records_and_is_idempotent(tmp_path):
    path = tmp_path / "nested" / "restaurant.db"
    assert db.initialize_database(path) == db.SCHEMA_VERSION
    assert db.initialize_database(path) == db.SCHEMA_VERSION
    with db.connect(path) as connection:
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0] == db.SCHEMA_VERSION
        assert connection.execute("SELECT COUNT(*) FROM restaurant").fetchone()[0] == 0
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert db.get_schema_version(path) == db.SCHEMA_VERSION


def test_data_survives_reinitialization(tmp_path):
    path = tmp_path / "restaurant.db"
    db.initialize_database(path)
    with db.connect(path) as connection:
        connection.execute("INSERT INTO dishes(id, name) VALUES ('custom', 'Custom Dish')")
    db.initialize_database(path)
    with db.connect(path) as connection:
        assert connection.execute("SELECT name FROM dishes WHERE id='custom'").fetchone()["name"] == "Custom Dish"


def test_connection_rolls_back_failed_transaction(tmp_path):
    path = tmp_path / "restaurant.db"
    db.initialize_database(path)
    with pytest.raises(RuntimeError, match="stop"):
        with db.connect(path) as connection:
            connection.execute("INSERT INTO dishes(id, name) VALUES ('custom', 'Custom Dish')")
            raise RuntimeError("stop")
    with db.connect(path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM dishes").fetchone()[0] == 0


def test_migration_failure_rolls_back_schema_and_version(tmp_path, monkeypatch):
    migrations = tmp_path / "bad_migrations"
    migrations.mkdir()
    (migrations / "001_bad.sql").write_text("CREATE TABLE partial(id TEXT);\nTHIS IS NOT SQL;\n", encoding="utf-8")
    monkeypatch.setattr(db, "MIGRATIONS_DIR", migrations)
    path = tmp_path / "restaurant.db"
    with pytest.raises(sqlite3.OperationalError):
        db.initialize_database(path)
    with db.connect(path) as connection:
        tables = {row["name"] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "partial" not in tables
        assert "schema_migrations" not in tables


def test_modified_applied_migration_requires_new_version(tmp_path, monkeypatch):
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    original = db.MIGRATIONS_DIR / "001_initial.sql"
    target = migrations / original.name
    shutil.copyfile(original, target)
    monkeypatch.setattr(db, "MIGRATIONS_DIR", migrations)
    path = tmp_path / "restaurant.db"
    db.initialize_database(path)
    target.write_text(target.read_text(encoding="utf-8") + "\nCREATE TABLE unexpected(id TEXT);\n", encoding="utf-8")
    with pytest.raises(db.MigrationError, match="modified"):
        db.initialize_database(path)


def test_migration_checksum_ignores_windows_line_endings(tmp_path, monkeypatch):
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    original = db.MIGRATIONS_DIR / "001_initial.sql"
    target = migrations / original.name
    content = original.read_text(encoding="utf-8")
    target.write_bytes(content.encode("utf-8"))
    monkeypatch.setattr(db, "MIGRATIONS_DIR", migrations)
    path = tmp_path / "restaurant.db"
    db.initialize_database(path)
    target.write_bytes(content.replace("\n", "\r\n").encode("utf-8"))
    assert db.initialize_database(path) == 1


def test_foreign_keys_prevent_orphaned_recipe_items(tmp_path):
    path = tmp_path / "restaurant.db"
    db.initialize_database(path)
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
        with db.connect(path) as connection:
            connection.execute("INSERT INTO recipe_items VALUES ('orphan', 'missing', 'missing', '1', 'each')")


def test_seed_is_opt_in_idempotent_and_does_not_invent_predictions(tmp_path):
    path = tmp_path / "restaurant.db"
    db.initialize_database(path)
    with db.connect(path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 0
    first = seed_demo(path)
    second = seed_demo(path)
    assert first["seeded"] is True
    assert second["seeded"] is False
    assert first["counts"] == second["counts"]
    assert first["counts"]["documents"] == 5
    assert first["counts"]["receipts"] == 3
    assert first["counts"]["invoices"] == 2
    assert first["counts"]["forecast_runs"] == 0
    assert first["counts"]["alerts"] == 0
    with db.connect(path) as connection:
        assert connection.execute("SELECT is_demo FROM restaurant").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM documents WHERE is_demo != 1").fetchone()[0] == 0
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_seed_refuses_to_mix_with_existing_business_data(tmp_path):
    path = tmp_path / "restaurant.db"
    db.initialize_database(path)
    with db.connect(path) as connection:
        connection.execute("INSERT INTO dishes VALUES ('real_dish', 'Real Dish')")
    with pytest.raises(ValueError, match="already contains"):
        seed_demo(path)
    with db.connect(path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM dishes").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 0


def test_receipt_and_invoice_totals_reconcile_with_decimal_arithmetic(tmp_path):
    path = tmp_path / "restaurant.db"
    seed_demo(path)
    with db.connect(path) as connection:
        for invoice in connection.execute("SELECT * FROM invoices"):
            lines = connection.execute("SELECT * FROM invoice_lines WHERE invoice_id=?", (invoice["id"],)).fetchall()
            subtotal = Decimal("0.00")
            for line in lines:
                assert Decimal(line["quantity"]) * Decimal(line["unit_price"]) == Decimal(line["line_total"])
                subtotal += Decimal(line["line_total"])
                assert line["description"] in line["source_text"]
            assert subtotal == Decimal(invoice["subtotal"])
            assert subtotal + Decimal(invoice["tax"]) + Decimal(invoice["freight"]) == Decimal(invoice["total"])
        for receipt in connection.execute("SELECT * FROM receipts"):
            items = connection.execute("SELECT * FROM receipt_items WHERE receipt_id=?", (receipt["id"],)).fetchall()
            gross = sum((Decimal(item["gross_amount"]) for item in items), Decimal("0.00"))
            net = sum((Decimal(item["net_amount"]) for item in items), Decimal("0.00"))
            assert gross == Decimal(receipt["subtotal"])
            assert net + Decimal(receipt["tax"]) + Decimal(receipt["tip"]) == Decimal(receipt["total"])
            assert all(Decimal(item["quantity"]) * Decimal(item["unit_price"]) == Decimal(item["gross_amount"]) for item in items)


def test_seed_prices_and_recipe_support_documented_costs(tmp_path):
    path = tmp_path / "restaurant.db"
    seed_demo(path)
    with db.connect(path) as connection:
        beef = connection.execute("SELECT effective_date, unit_cost FROM ingredient_prices WHERE ingredient_id='beef' ORDER BY effective_date").fetchall()
        assert [row["unit_cost"] for row in beef] == ["4.00", "4.72"]
        recipe = connection.execute("SELECT ingredient_id, quantity FROM recipe_items WHERE recipe_version_id='recipe_classic_burger_v1'").fetchall()
        for day, expected in [("2026-11-06", "3.60"), ("2026-11-07", "3.96")]:
            cost = Decimal("0.00")
            for item in recipe:
                price = connection.execute("SELECT unit_cost FROM ingredient_prices WHERE ingredient_id=? AND effective_date<=? ORDER BY effective_date DESC LIMIT 1", (item["ingredient_id"], day)).fetchone()
                cost += Decimal(item["quantity"]) * Decimal(price["unit_cost"])
            assert cost == Decimal(expected)
        coverage = connection.execute("SELECT status FROM daily_coverage WHERE date='2026-11-07' ORDER BY channel_id").fetchall()
        assert {row["status"] for row in coverage} == {"unknown", "partial"}


def test_unique_document_hash_and_business_receipt_key_prevent_duplicates(tmp_path):
    path = tmp_path / "restaurant.db"
    seed_demo(path)
    with db.connect(path) as connection:
        document = dict(connection.execute("SELECT * FROM documents LIMIT 1").fetchone())
    document["id"] = "different_id"
    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):
        with db.connect(path) as connection:
            connection.execute(f"INSERT INTO documents({','.join(document)}) VALUES ({','.join('?' for _ in document)})", tuple(document.values()))
    with db.connect(path) as connection:
        receipt = dict(connection.execute("SELECT * FROM receipts WHERE id='receipt_001'").fetchone())
        other_document = "doc_invoice_baseline"
    receipt.update(id="duplicate_receipt", document_id=other_document)
    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):
        with db.connect(path) as connection:
            connection.execute(f"INSERT INTO receipts({','.join(receipt)}) VALUES ({','.join('?' for _ in receipt)})", tuple(receipt.values()))


def test_unknown_channel_receipt_key_is_also_unique(tmp_path):
    path = tmp_path / "restaurant.db"
    seed_demo(path)
    with db.connect(path) as connection:
        connection.execute("UPDATE receipts SET channel_id=NULL WHERE id='receipt_001'")
        receipt = dict(connection.execute("SELECT * FROM receipts WHERE id='receipt_001'").fetchone())
    receipt.update(id="duplicate_unknown", document_id="doc_invoice_baseline")
    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):
        with db.connect(path) as connection:
            connection.execute(f"INSERT INTO receipts({','.join(receipt)}) VALUES ({','.join('?' for _ in receipt)})", tuple(receipt.values()))


@pytest.mark.parametrize("bad_value", ["oops", "", " ", ".50", "01", "1.", "1.2.3", "1e2", "-1", "+1", "0.123456789"])
def test_database_rejects_noncanonical_decimal_text(tmp_path, bad_value):
    path = tmp_path / "restaurant.db"
    seed_demo(path)
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        with db.connect(path) as connection:
            connection.execute("UPDATE ingredient_prices SET unit_cost=? WHERE id='price_invoice_baseline_beef'", (bad_value,))


def test_database_units_match_supported_contract(tmp_path):
    path = tmp_path / "restaurant.db"
    seed_demo(path)
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        with db.connect(path) as connection:
            connection.execute("INSERT INTO ingredients(id,name,base_unit) VALUES ('rice', 'Rice', 'kg')")


def test_seed_source_quotes_are_exact_and_hashes_match(tmp_path):
    path = tmp_path / "restaurant.db"
    seed_demo(path)
    with db.connect(path) as connection:
        documents = {row["id"]: row for row in connection.execute("SELECT * FROM documents")}
        for document in documents.values():
            assert document["source_text"].startswith("SYNTHETIC FIXTURE")
            assert hashlib.sha256(document["source_text"].encode("utf-8")).hexdigest() == document["sha256"]
        for line in connection.execute("SELECT invoice_lines.source_text,invoices.document_id FROM invoice_lines JOIN invoices ON invoices.id=invoice_lines.invoice_id"):
            assert line["source_text"] in documents[line["document_id"]]["source_text"]
        for line in connection.execute("SELECT receipt_items.source_text,receipts.document_id FROM receipt_items JOIN receipts ON receipts.id=receipt_items.receipt_id"):
            assert line["source_text"] in documents[line["document_id"]]["source_text"]


def test_seed_cli_is_explicit_and_returns_safe_json(tmp_path, capsys):
    path = tmp_path / "cli.db"
    assert main(["--database", str(path)]) == 0
    first = json.loads(capsys.readouterr().out)
    assert first["seeded"] is True
    assert main(["--database", str(path)]) == 0
    assert json.loads(capsys.readouterr().out)["seeded"] is False


def test_seed_cli_default_uses_configured_database(tmp_path, capsys, monkeypatch):
    path = tmp_path / "configured.db"
    monkeypatch.setenv("MARGINGUARD_DATABASE_PATH", str(path))
    assert main([]) == 0
    assert path.exists()
    assert json.loads(capsys.readouterr().out)["seeded"] is True


def test_seed_cli_fails_clearly_without_resetting_existing_data(tmp_path, capsys):
    path = tmp_path / "business.db"
    db.initialize_database(path)
    with db.connect(path) as connection:
        connection.execute("INSERT INTO dishes(id,name) VALUES ('real', 'Existing Dish')")
    with pytest.raises(SystemExit) as exc:
        main(["--database", str(path)])
    assert exc.value.code == 2
    assert "already contains business records" in capsys.readouterr().err
    with db.connect(path) as connection:
        assert connection.execute("SELECT name FROM dishes WHERE id='real'").fetchone()[0] == "Existing Dish"
