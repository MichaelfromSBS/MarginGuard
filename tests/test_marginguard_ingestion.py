"""Checkpoint-two upload, approval, review and retry integration boundaries."""
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.config import ROOT, Settings
from backend.main import create_app
from backend.marginguard.db import connect
from backend.marginguard.extraction import ExtractionError
from backend.marginguard.schemas import DocumentDetail, InvoiceExtraction, ReceiptExtraction
from backend.marginguard.seed import seed_demo

DATA = ROOT / "demo_data"
INVOICE = "live_demo/2_invoice_RF-20261107-004"
RECEIPT = "live_demo/1_receipt_TB-20261107-001"
IMAGE = "live_demo/3_receipt_TB-20261107-002_photo"


def extraction(relative):
    payload = json.loads((DATA / (relative + ".expected.json")).read_text(encoding="utf-8"))
    model = InvoiceExtraction if "invoice_number" in payload else ReceiptExtraction
    return model.model_validate(payload)


class SequenceExtractor:
    """Explicit test injection, never an implicit production sidecar fallback."""
    def __init__(self, *values):
        self.values = list(values)
        self.calls = 0

    async def __call__(self, client, settings, document_type, prepared, catalog, restaurant_timezone):
        self.calls += 1
        assert {"ingredients", "dishes", "channels"}.issubset(catalog)
        assert restaurant_timezone == "America/New_York"
        value = self.values.pop(0)
        if isinstance(value, Exception):
            raise value
        assert document_type == ("invoice" if isinstance(value, InvoiceExtraction) else "receipt")
        return value


@contextmanager
def client_for(tmp_path, extractor=None, *, seed=True):
    database = tmp_path / "ledger.db"
    if seed:
        seed_demo(database)
    settings = Settings(_env_file=None, database_path=database, upload_directory=tmp_path / "uploads")
    app = create_app(settings, document_extractor=extractor)
    with TestClient(app) as client:
        yield client, database, settings


def upload(client, relative, *, image=False, filename=None, document_type=None):
    model = extraction(relative)
    kind = document_type or ("invoice" if isinstance(model, InvoiceExtraction) else "receipt")
    path = DATA / (relative + (".png" if image else ".pdf"))
    return client.post("/api/documents", data={"document_type": kind}, files={
        "file": (filename or path.name, path.read_bytes(), "image/png" if image else "application/pdf"),
    })


def detail(client, response):
    assert response.status_code == 202, response.text
    result = client.get("/api/documents/" + response.json()["id"])
    assert result.status_code == 200, result.text
    DocumentDetail.model_validate(result.json())
    return result.json()


def counts(database):
    with connect(database) as conn:
        return {name: conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0] for name in [
            "documents", "invoices", "invoice_lines", "ingredient_prices", "receipts", "receipt_items", "data_changes", "alerts", "forecast_runs",
        ]} | {"data_version": conn.execute("SELECT data_version FROM restaurant").fetchone()[0]}


def test_invoice_and_receipt_uploads_approve_real_source_documents_atomically(tmp_path):
    fake = SequenceExtractor(extraction(INVOICE), extraction(RECEIPT))
    with client_for(tmp_path, fake) as (client, database, settings):
        before = counts(database)
        invoice = detail(client, upload(client, INVOICE, filename="../../supplier.pdf"))
        receipt = detail(client, upload(client, RECEIPT))
        assert invoice["status"] == receipt["status"] == "completed"
        assert invoice["evidence_mode"] == receipt["evidence_mode"] == "text"
        assert invoice["page_count"] == receipt["page_count"] == 1
        assert invoice["validation_issues"] == receipt["validation_issues"] == []
        assert invoice["filename"] == "supplier.pdf"
        assert invoice["extraction"]["invoice_number"] == "RF-20261107-004"
        assert all(item["source_text"] in invoice["source_text"] for item in invoice["extraction"]["items"])
        after = counts(database)
        assert after["invoices"] == before["invoices"] + 1
        assert after["receipts"] == before["receipts"] + 1
        assert after["data_version"] == before["data_version"] + 2
        assert after["data_changes"] == before["data_changes"] + 2
        assert after["alerts"] == after["forecast_runs"] == 0
        with connect(database) as conn:
            price = conn.execute("SELECT unit_cost,base_unit FROM ingredient_prices p JOIN invoice_lines l ON l.id=p.invoice_line_id JOIN invoices i ON i.id=l.invoice_id WHERE i.document_id=?", (invoice["id"],)).fetchone()
            assert tuple(price) == ("4.72", "lb")
            stored = conn.execute("SELECT storage_path,sha256 FROM documents WHERE id=?", (invoice["id"],)).fetchone()
            assert Path(stored["storage_path"]).is_relative_to(settings.upload_directory)
            assert hashlib.sha256(Path(stored["storage_path"]).read_bytes()).hexdigest() == stored["sha256"]


def test_same_bytes_return_original_document_without_another_model_call_or_ledger_write(tmp_path):
    fake = SequenceExtractor(extraction(RECEIPT))
    with client_for(tmp_path, fake) as (client, database, _):
        first = detail(client, upload(client, RECEIPT))
        before = counts(database)
        second = upload(client, RECEIPT, filename="renamed.pdf")
        assert second.status_code in {200, 202}, second.text
        assert second.json()["id"] == first["id"]
        assert fake.calls == 1
        assert counts(database) == before


def test_same_bytes_cannot_be_reclassified_as_another_document_type(tmp_path):
    fake = SequenceExtractor(extraction(RECEIPT))
    with client_for(tmp_path, fake) as (client, database, _):
        detail(client, upload(client, RECEIPT))
        before = counts(database)
        response = upload(client, RECEIPT, document_type="invoice")
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "document_type_conflict"
        assert counts(database) == before


def test_different_bytes_same_business_key_require_review_without_double_counting(tmp_path):
    conflict = "edge_cases/E2_conflicting_RF-20261107-004"
    fake = SequenceExtractor(extraction(INVOICE), extraction(conflict))
    with client_for(tmp_path, fake) as (client, database, _):
        approved = detail(client, upload(client, INVOICE))
        before = counts(database)
        result = detail(client, upload(client, conflict))
        assert result["status"] == "needs_review"
        issue = next(item for item in result["validation_issues"] if item["code"] == "business_key_conflict")
        assert issue["existing_document_id"] == approved["id"]
        after = counts(database)
        for key in ["invoices", "invoice_lines", "ingredient_prices", "data_changes", "data_version"]:
            assert after[key] == before[key]


@pytest.mark.parametrize("relative,expected", [
    ("edge_cases/E4_needs_review_APC-20261107-01", {"unmapped_vendor", "unmapped_ingredient", "missing_pack_size"}),
    ("edge_cases/E4b_unknown_dish_TB-20261107-003", {"unmapped_dish"}),
])
def test_ambiguous_documents_preserve_extraction_but_not_approved_financial_records(tmp_path, relative, expected):
    with client_for(tmp_path, SequenceExtractor(extraction(relative))) as (client, database, _):
        before = counts(database)
        result = detail(client, upload(client, relative))
        assert result["status"] == "needs_review"
        assert expected.issubset({item["code"] for item in result["validation_issues"]})
        assert result["extraction"] is not None
        after = counts(database)
        for key in ["invoices", "invoice_lines", "ingredient_prices", "receipts", "receipt_items", "data_changes", "data_version"]:
            assert after[key] == before[key]


def test_review_corrects_a_missing_channel_then_prevents_overwriting_approved_records(tmp_path):
    real = extraction(RECEIPT)
    incomplete = real.model_copy(update={"channel_id": None})
    with client_for(tmp_path, SequenceExtractor(incomplete)) as (client, database, _):
        result = detail(client, upload(client, RECEIPT))
        assert result["status"] == "needs_review"
        before = counts(database)
        payload = {"document_type": "receipt", "extraction": real.model_dump(mode="json"), "note": "Confirmed the printed dine-in channel."}
        reviewed = client.post(f"/api/documents/{result['id']}/review", json=payload)
        assert reviewed.status_code == 200, reviewed.text
        assert reviewed.json()["status"] == "completed"
        assert reviewed.json()["extraction_method"] == "manual_review"
        assert reviewed.json()["reviewed_at"]
        assert reviewed.json()["review_note"] == payload["note"]
        after = counts(database)
        assert after["receipts"] == before["receipts"] + 1
        assert after["data_version"] == before["data_version"] + 1
        assert client.post(f"/api/documents/{result['id']}/review", json=payload).status_code == 409
        assert counts(database) == after


def test_review_must_still_pass_math_and_source_validation(tmp_path):
    real = extraction(RECEIPT)
    incomplete = real.model_copy(update={"channel_id": None})
    with client_for(tmp_path, SequenceExtractor(incomplete)) as (client, database, _):
        result = detail(client, upload(client, RECEIPT))
        before = counts(database)
        invalid = real.model_dump(mode="json")
        invalid["total"] = "99.00"
        response = client.post(f"/api/documents/{result['id']}/review", json={"document_type": "receipt", "extraction": invalid})
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "needs_review"
        assert "receipt_total_mismatch" in {item["code"] for item in response.json()["validation_issues"]}
        assert counts(database)["receipts"] == before["receipts"]
        assert counts(database)["data_version"] == before["data_version"]


def test_failed_model_call_is_retryable_but_approved_document_is_not(tmp_path):
    fake = SequenceExtractor(ExtractionError("provider_unavailable", "Model unavailable."), extraction(INVOICE))
    with client_for(tmp_path, fake) as (client, database, _):
        before = counts(database)
        result = detail(client, upload(client, INVOICE))
        assert result["status"] == "failed"
        assert result["error_code"] == "provider_unavailable"
        assert counts(database)["data_version"] == before["data_version"]
        response = client.post(f"/api/documents/{result['id']}/process")
        assert response.status_code == 202, response.text
        finished = client.get(f"/api/documents/{result['id']}").json()
        assert finished["status"] == "completed"
        assert fake.calls == 2
        assert client.post(f"/api/documents/{result['id']}/process").status_code == 409


def test_mock_mode_never_silently_approves_sidecar_data(tmp_path):
    with client_for(tmp_path) as (client, database, _):
        before = counts(database)
        result = detail(client, upload(client, INVOICE))
        assert result["status"] == "failed"
        assert result["error_code"] == "live_model_required"
        assert counts(database)["invoices"] == before["invoices"]
        assert counts(database)["data_version"] == before["data_version"]


def test_image_approval_is_labeled_visual_without_claiming_text_verification(tmp_path):
    with client_for(tmp_path, SequenceExtractor(extraction(IMAGE))) as (client, _, _):
        result = detail(client, upload(client, IMAGE, image=True))
        assert result["status"] == "completed"
        assert result["evidence_mode"] == "visual"
        assert result["source_text"] is None
        assert result["page_count"] == 1
        assert result["extraction"]["items"]


def test_upload_rejects_unsupported_bytes_and_mime_mismatch_without_creating_records(tmp_path):
    with client_for(tmp_path, SequenceExtractor()) as (client, database, _):
        before = counts(database)
        unsupported = client.post("/api/documents", data={"document_type": "invoice"}, files={"file": ("data.txt", b"hello", "text/plain")})
        assert unsupported.status_code == 415
        wrong_mime = client.post("/api/documents", data={"document_type": "invoice"}, files={"file": ("data.pdf", (DATA / (INVOICE + ".pdf")).read_bytes(), "image/png")})
        assert wrong_mime.status_code == 415
        assert counts(database) == before


def test_invalid_pdf_is_preserved_for_review_without_calling_model(tmp_path):
    fake = SequenceExtractor()
    with client_for(tmp_path, fake) as (client, database, _):
        before = counts(database)
        response = client.post("/api/documents", data={"document_type": "invoice"}, files={"file": ("broken.pdf", b"%PDF-1.4\nnot a valid document\n", "application/pdf")})
        result = detail(client, response)
        assert result["status"] == "needs_review"
        assert result["error_code"]
        assert fake.calls == 0
        assert counts(database)["data_version"] == before["data_version"]


def test_late_invoice_extends_history_without_replacing_newest_effective_price(tmp_path):
    old = "edge_cases/E5_late_arrival_RF-20261030-002"
    with client_for(tmp_path, SequenceExtractor(extraction(INVOICE), extraction(old))) as (client, _, _):
        assert detail(client, upload(client, INVOICE))["status"] == "completed"
        assert detail(client, upload(client, old))["status"] == "completed"
        history = client.get("/api/ingredients/beef/prices").json()["items"]
        assert history[0]["effective_date"] == "2026-10-30"
        assert history[0]["unit_cost"] == "4.1"
        assert history[-1]["effective_date"] == "2026-11-07"
        assert history[-1]["unit_cost"] == "4.72"


def test_new_receipt_marks_the_day_partial_and_never_assumes_it_is_complete(tmp_path):
    real = extraction(RECEIPT)
    with client_for(tmp_path, SequenceExtractor(real)) as (client, database, _):
        with connect(database) as conn:
            conn.execute("UPDATE daily_coverage SET status='complete' WHERE date='2026-11-07' AND channel_id='in_store'")
        assert detail(client, upload(client, RECEIPT))["status"] == "completed"
        rows = client.get("/api/coverage").json()["items"]
        current = next(row for row in rows if row["date"] == "2026-11-07" and row["channel_id"] == "in_store")
        assert current["status"] == "partial"


def test_unconfigured_database_rejects_upload_without_saving_customer_files(tmp_path):
    with client_for(tmp_path, SequenceExtractor(extraction(INVOICE)), seed=False) as (client, _, settings):
        response = upload(client, INVOICE)
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "restaurant_not_configured"
        assert not settings.upload_directory.exists() or not list(settings.upload_directory.iterdir())


def test_tampered_source_is_not_extracted_or_served(tmp_path):
    fake = SequenceExtractor(ExtractionError("temporary_failure", "Try again."))
    with client_for(tmp_path, fake) as (client, database, _):
        result = detail(client, upload(client, RECEIPT))
        assert result["status"] == "failed"
        with connect(database) as conn:
            path = Path(conn.execute("SELECT storage_path FROM documents WHERE id=?", (result["id"],)).fetchone()[0])
        path.write_bytes(path.read_bytes() + b"\nchanged")
        assert client.get(f"/api/documents/{result['id']}/source").status_code == 409
        retry = detail(client, client.post(f"/api/documents/{result['id']}/process"))
        assert retry["error_code"] == "source_integrity_failed"
        assert fake.calls == 1
