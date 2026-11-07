import hashlib
import json
import shutil
import subprocess
import sys

import pytest

from backend.config import ROOT
from backend.marginguard.db import connect
from backend.marginguard.import_demo import DEFAULT_SOURCE, import_demo
from backend.marginguard.seed import seed_demo


def counts(path):
    with connect(path) as conn:
        return {table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in ["restaurant", "documents", "invoices", "receipts", "ingredient_prices", "data_changes", "import_batches", "alerts", "forecast_runs"]}


def copy_source(tmp_path):
    destination = tmp_path / "source"
    shutil.copytree(DEFAULT_SOURCE, destination)
    return destination


def test_full_v2_history_import_is_explicit_validated_and_idempotent(tmp_path):
    path = tmp_path / "history.db"
    first = import_demo(path)
    second = import_demo(path)
    assert first["imported"] is True and second["imported"] is False
    assert first["source_fingerprint"] == second["source_fingerprint"]
    assert first["receipt_count"] == second["receipt_count"] == 2733
    assert first["invoice_count"] == second["invoice_count"] == 8
    assert counts(path) == {"restaurant": 1, "documents": 2741, "invoices": 8, "receipts": 2733, "ingredient_prices": 40, "data_changes": 2741, "import_batches": 1, "alerts": 0, "forecast_runs": 0}
    with connect(path) as conn:
        assert conn.execute("SELECT data_version FROM restaurant").fetchone()[0] == 2741
        assert conn.execute("SELECT COUNT(*) FROM documents WHERE status='completed' AND is_demo=1 AND extraction_method='fixture_history'").fetchone()[0] == 2741
        assert conn.execute("SELECT COUNT(*) FROM documents WHERE storage_path IS NOT NULL").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM vendors").fetchone()[0] == 1
        assert conn.execute("SELECT is_open FROM restaurant_calendar WHERE date='2026-12-25'").fetchone()[0] == 0
        assert conn.execute("SELECT status FROM daily_coverage WHERE date='2026-10-14' AND channel_id='in_store'").fetchone()[0] == "unknown"
        assert conn.execute("SELECT status FROM daily_coverage WHERE date='2026-11-07' AND channel_id='in_store'").fetchone()[0] == "partial"
        assert conn.execute("SELECT status FROM daily_coverage WHERE date='2026-11-06' AND channel_id='delivery'").fetchone()[0] == "complete"
        assert conn.execute("SELECT unit_cost FROM ingredient_prices WHERE ingredient_id='beef' ORDER BY effective_date DESC LIMIT 1").fetchone()[0] == "4"
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_import_preserves_source_provenance_and_actual_pdf_hash(tmp_path):
    path = tmp_path / "history.db"
    import_demo(path)
    pdf = DEFAULT_SOURCE / "history/invoices/RF-20260915-001.pdf"
    with connect(path) as conn:
        document = conn.execute("SELECT * FROM documents WHERE filename=?", (pdf.name,)).fetchone()
        assert document["sha256"] == hashlib.sha256(pdf.read_bytes()).hexdigest()
        assert document["evidence_mode"] == "text"
        lines = conn.execute("SELECT source_text FROM invoice_lines WHERE invoice_id=(SELECT id FROM invoices WHERE document_id=?)", (document["id"],)).fetchall()
        assert all(row["source_text"] in document["source_text"] for row in lines)
        receipt = conn.execute("SELECT * FROM documents WHERE type='receipt' ORDER BY id LIMIT 1").fetchone()
        assert receipt["sha256"] == hashlib.sha256(receipt["source_text"].encode("utf-8")).hexdigest()
        items = conn.execute("SELECT source_text FROM receipt_items WHERE receipt_id=(SELECT id FROM receipts WHERE document_id=?)", (receipt["id"],)).fetchall()
        assert all(row["source_text"] in receipt["source_text"] for row in items)


def test_import_refuses_to_mix_with_checkpoint_one_seed(tmp_path):
    path = tmp_path / "existing.db"
    seed_demo(path)
    before = counts(path)
    with pytest.raises(ValueError, match="Refusing to mix"):
        import_demo(path)
    assert counts(path) == before


def test_late_bad_receipt_rolls_back_entire_ledger_import(tmp_path):
    source = copy_source(tmp_path)
    receipt_file = source / "history/receipts.jsonl"
    records = receipt_file.read_text().splitlines()
    last = json.loads(records[-1])
    last["total"] = "9999.00"
    records[-1] = json.dumps(last)
    receipt_file.write_text("\n".join(records) + "\n")
    path = tmp_path / "rollback.db"
    with pytest.raises(ValueError, match="failed approval"):
        import_demo(path, source)
    assert all(value == 0 for value in counts(path).values())
    with connect(path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM ingredients").fetchone()[0] == 0


def test_duplicate_or_unpaired_receipt_sources_are_rejected(tmp_path):
    source = copy_source(tmp_path)
    path = source / "history/receipt_sources.jsonl"
    lines = path.read_text().splitlines()
    path.write_text("\n".join(lines + [lines[0]]) + "\n")
    with pytest.raises(ValueError, match="Duplicate receipt"):
        import_demo(tmp_path / "bad.db", source)


def test_changed_corpus_does_not_silently_reseed_an_imported_database(tmp_path):
    path = tmp_path / "history.db"
    import_demo(path)
    before = counts(path)
    source = copy_source(tmp_path)
    policy = source / "config/demo_policy.json"
    policy.write_text(policy.read_text() + "\n")
    with pytest.raises(ValueError, match="Refusing to mix"):
        import_demo(path, source)
    assert counts(path) == before


def test_cli_import_requires_explicit_database_and_prints_safe_summary(tmp_path):
    result = subprocess.run([sys.executable, "-m", "backend.marginguard.import_demo", "--database", str(tmp_path / "cli.db")], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    assert summary["imported"] is True
    assert summary["invoice_count"] == 8 and summary["receipt_count"] == 2733
    missing = subprocess.run([sys.executable, "-m", "backend.marginguard.import_demo"], cwd=ROOT, capture_output=True, text=True)
    assert missing.returncode != 0
    assert "--database" in missing.stderr
