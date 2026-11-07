"""Checkpoint 2: accepted uploads, bounded request-process tasks and atomic ledger approval.

No directory watcher, forecasting, anomaly alerts or notification sending lives here.
Pending jobs are durable; manual process/retry resumes them until checkpoint 4 adds a worker.
"""
import asyncio
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from uuid import uuid4
from zoneinfo import ZoneInfo

from .db import connect
from .document_io import DocumentReadError, read_document
from .errors import DomainError
from .extraction import ExtractionError, extract_document
from .schemas import Document, DocumentDetail, InvoiceExtraction, ReceiptExtraction
from .validation import validate_extraction


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def identifier(prefix: str) -> str:
    return prefix + "_" + uuid4().hex


def insert(conn, table: str, **values):
    conn.execute(f"INSERT INTO {table} ({','.join(values)}) VALUES ({','.join('?' for _ in values)})", tuple(values.values()))


def restaurant_record(conn):
    row = conn.execute("SELECT * FROM restaurant ORDER BY id LIMIT 1").fetchone()
    if row is None:
        raise DomainError("restaurant_not_configured", "Configure a restaurant or explicitly load the demo before uploading documents.", 409)
    return dict(row)


def extraction_catalog(conn) -> dict:
    ingredients = []
    for row in conn.execute("SELECT * FROM ingredients ORDER BY id"):
        value = dict(row)
        value["aliases"] = json.loads(value.pop("aliases_json"))
        ingredients.append(value)
    return {
        "ingredients": ingredients,
        "dishes": [dict(r) for r in conn.execute("SELECT * FROM dishes ORDER BY id")],
        "channels": [dict(r) for r in conn.execute("SELECT * FROM channels ORDER BY id")],
        "vendors": [{"id": r["id"], "name": r["name"], "aliases": json.loads(r["aliases_json"])} for r in conn.execute("SELECT * FROM vendors ORDER BY id")],
    }


def document_payload(row, *, detail=False):
    value = dict(row)
    result = {name: value[name] for name in Document.model_fields}
    if detail:
        result.update({
            "source_text": value["source_text"], "page_count": value["page_count"],
            "evidence_mode": value["evidence_mode"], "extraction_method": value["extraction_method"],
            "extraction": json.loads(value["extraction_json"]) if value["extraction_json"] else None,
            "validation_issues": json.loads(value["validation_issues_json"]),
            "reviewed_at": value["reviewed_at"], "review_note": value["review_note"],
        })
    return result


def get_document(database: Path, document_id: str, *, detail=False):
    with connect(database) as conn:
        row = conn.execute("SELECT * FROM documents WHERE id=?", (document_id,)).fetchone()
        if row is None:
            raise DomainError("document_not_found", "Document does not exist.", 404, document_id=document_id)
        return document_payload(row, detail=detail)


def media_type(data: bytes, declared: str | None) -> tuple[str, str]:
    if not data:
        raise DomainError("empty_file", "The uploaded file is empty.", 422)
    if len(data) > 4 * 1024 * 1024:
        raise DomainError("file_too_large", "Files must be no larger than 4 MB; images no larger than 3 MB.", 413)
    if data.startswith(b"%PDF-"):
        detected, extension = "application/pdf", ".pdf"
    elif data.startswith(b"\x89PNG\r\n\x1a\n"):
        detected, extension = "image/png", ".png"
    elif data.startswith(b"\xff\xd8\xff"):
        detected, extension = "image/jpeg", ".jpg"
    else:
        raise DomainError("unsupported_media_type", "Upload a readable PDF, PNG or JPEG document.", 415)
    if declared and declared not in {detected, "application/octet-stream"}:
        raise DomainError("media_type_mismatch", "The declared file type does not match its content.", 415)
    if detected.startswith("image/") and len(data) > 3 * 1024 * 1024:
        raise DomainError("file_too_large", "Images must be no larger than 3 MB.", 413)
    return detected, extension


def register_upload(settings, document_type: str, filename: str, declared: str | None, data: bytes) -> tuple[dict, bool]:
    detected, extension = media_type(data, declared)
    sha = hashlib.sha256(data).hexdigest()
    with connect(settings.database_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        owner = restaurant_record(conn)
        existing = conn.execute("SELECT * FROM documents WHERE sha256=?", (sha,)).fetchone()
        if existing:
            if existing["type"] != document_type:
                raise DomainError("document_type_conflict", "These bytes were already registered as a different document type.", 409)
            return document_payload(existing), True
        doc_id, stamp = identifier("doc"), now()
        settings.upload_directory.mkdir(parents=True, exist_ok=True)
        path = settings.upload_directory / (doc_id + extension)
        # The generated name never uses a client-supplied path; exclusive creation.
        with path.open("xb") as output:
            output.write(data)
        safe_name = (filename or ("document" + extension)).replace("\\", "/").split("/")[-1].replace("\x00", "")[:200]
        insert(conn, "documents", id=doc_id, type=document_type, filename=safe_name,
               sha256=sha, media_type=detected, status="detected", created_at=stamp,
               updated_at=stamp, is_demo=owner["is_demo"], storage_path=str(path.resolve()),
               evidence_mode="unavailable")
        insert(conn, "processing_jobs", id=identifier("job"), document_id=doc_id,
               kind="extract_document", status="pending", attempts=0, created_at=stamp, updated_at=stamp)
        return document_payload(conn.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()), False


def conflict_issue(conn, extraction):
    if isinstance(extraction, InvoiceExtraction):
        row = conn.execute("SELECT id,document_id FROM invoices WHERE lower(trim(vendor_id))=lower(?) AND lower(trim(invoice_number))=lower(?)", (extraction.vendor_id or "", extraction.invoice_number.strip())).fetchone()
    else:
        row = conn.execute("SELECT id,document_id FROM receipts WHERE COALESCE(channel_id,'')=COALESCE(?,'') AND lower(trim(receipt_number))=lower(?)", (extraction.channel_id, extraction.receipt_number.strip())).fetchone()
    if row:
        return {"code": "business_key_conflict", "message": "A different document already owns this invoice or receipt key; it was not counted again.", "item_index": None, "existing_document_id": row["document_id"]}
    return None


def persist_ledger(conn, document_id: str, extraction, normalized_prices, stamp: str):
    """Caller owns the approval transaction and has completed business validation."""
    record_id = identifier("invoice" if isinstance(extraction, InvoiceExtraction) else "receipt")
    if isinstance(extraction, InvoiceExtraction):
        insert(conn, "invoices", id=record_id, document_id=document_id,
               vendor_id=extraction.vendor_id, vendor_name=extraction.vendor_name,
               invoice_number=extraction.invoice_number.strip(), invoice_date=extraction.invoice_date.isoformat(),
               currency=extraction.currency, subtotal=extraction.subtotal, tax=extraction.tax,
               freight=extraction.freight, total=extraction.total)
        by_index = {p.item_index: p for p in normalized_prices}
        for index, item in enumerate(extraction.items):
            line_id = identifier("line")
            insert(conn, "invoice_lines", id=line_id, invoice_id=record_id, **item.model_dump())
            price = by_index[index]
            insert(conn, "ingredient_prices", id=identifier("price"), ingredient_id=price.ingredient_id,
                   invoice_line_id=line_id, effective_date=extraction.invoice_date.isoformat(),
                   unit_cost=price.unit_cost, base_unit=price.base_unit)
    else:
        owner = restaurant_record(conn)
        local_day = extraction.sold_at.astimezone(ZoneInfo(owner["timezone"])).date().isoformat()
        values = extraction.model_dump(exclude={"items", "sold_at"})
        values["receipt_number"] = values["receipt_number"].strip()
        insert(conn, "receipts", id=record_id, document_id=document_id,
               sold_at=extraction.sold_at.isoformat(), local_date=local_day, **values)
        for item in extraction.items:
            insert(conn, "receipt_items", id=identifier("item"), receipt_id=record_id, **item.model_dump())
        conn.execute("""INSERT INTO daily_coverage(date,channel_id,status,updated_at) VALUES (?,?,'partial',?)
                     ON CONFLICT(date,channel_id) DO UPDATE SET status='partial',updated_at=excluded.updated_at""",
                     (local_day, extraction.channel_id, stamp))
    conn.execute("UPDATE restaurant SET data_version=data_version+1")
    version = restaurant_record(conn)["data_version"]
    insert(conn, "data_changes", source_data_version=version, document_id=document_id,
           change_type="invoice_approved" if isinstance(extraction, InvoiceExtraction) else "receipt_approved", created_at=stamp)
    # An approved source change must never leave an old forecast presented as ready.
    conn.execute("UPDATE forecast_runs SET status='pending' WHERE status='ready'")
    return record_id


def approve_extraction(conn, doc_id, extraction, source_pages, *, image=False, method="openrouter", review_note=None):
    """Validate and atomically approve one whole document, or persist review issues."""
    document = conn.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()
    owner = restaurant_record(conn)
    kind = "invoice" if isinstance(extraction, InvoiceExtraction) else "receipt"
    if document["type"] != kind:
        raise DomainError("document_type_conflict", "The review type does not match the stored document.", 422)
    validation = validate_extraction(extraction, kind, extraction_catalog(conn), source_pages, owner["timezone"], image=image)
    issues = [asdict(issue) for issue in validation.issues]
    conflict = conflict_issue(conn, extraction)
    if conflict:
        issues.append(conflict)
    stamp = now()
    result = "needs_review" if issues else "completed"
    encoded = extraction.model_dump_json()
    if not issues:
        persist_ledger(conn, doc_id, extraction, validation.normalized_prices, stamp)
    conn.execute("""UPDATE documents SET status=?,updated_at=?,extraction_json=?,extraction_method=?,
                 validation_issues_json=?,error_code=?,error_message=? WHERE id=?""",
                 (result, stamp, encoded, method, json.dumps(issues), issues[0]["code"] if issues else None,
                  issues[0]["message"] if issues else None, doc_id))
    conn.execute("UPDATE processing_jobs SET status='completed',updated_at=?,error_message=NULL WHERE document_id=? AND status IN ('pending','processing')", (stamp, doc_id))
    if review_note is not None:
        conn.execute("UPDATE documents SET reviewed_at=?,review_note=? WHERE id=?", (stamp, review_note, doc_id))
        insert(conn, "review_events", id=identifier("review"), document_id=doc_id, created_at=stamp,
               note=review_note, extraction_json=encoded, outcome=result)
    return document_payload(conn.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone(), detail=True)


def mark_problem(database, document_id, code, message, *, review=False):
    with connect(database) as conn:
        stamp = now()
        issues = [{"code": code, "message": message, "item_index": None}]
        conn.execute("UPDATE documents SET status=?,updated_at=?,error_code=?,error_message=?,validation_issues_json=? WHERE id=?",
                     ("needs_review" if review else "failed", stamp, code, message, json.dumps(issues), document_id))
        conn.execute("UPDATE processing_jobs SET status='failed',updated_at=?,error_message=? WHERE document_id=? AND status IN ('pending','processing')", (stamp, message, document_id))


async def process_document(app, document_id: str):
    """Request-process background task; bounded, serialized, and manually resumable."""
    if document_id in app.state.active_documents:
        return
    app.state.active_documents.add(document_id)
    settings = app.state.settings
    try:
        async with app.state.ai_lock:
            with connect(settings.database_path) as conn:
                conn.execute("BEGIN IMMEDIATE")
                row = conn.execute("SELECT * FROM documents WHERE id=?", (document_id,)).fetchone()
                if row is None or row["status"] != "detected":
                    return
                stored = dict(row)
                conn.execute("UPDATE documents SET status='processing',updated_at=? WHERE id=?", (now(), document_id))
                conn.execute("UPDATE processing_jobs SET status='processing',attempts=attempts+1,updated_at=? WHERE document_id=? AND status='pending'", (now(), document_id))
                owner = restaurant_record(conn)
                catalog = extraction_catalog(conn)
            path = Path(stored["storage_path"])
            if not path.resolve().is_relative_to(settings.upload_directory.resolve()):
                raise DomainError("source_unavailable", "The stored document is outside the configured upload directory.", 409)
            data = await asyncio.to_thread(path.read_bytes)
            if hashlib.sha256(data).hexdigest() != stored["sha256"]:
                raise DomainError("source_integrity_failed", "The stored source bytes no longer match the uploaded document hash.", 409)
            prepared = await asyncio.to_thread(read_document, data, stored["media_type"])
            with connect(settings.database_path) as conn:
                conn.execute("UPDATE documents SET source_text=?,page_count=?,evidence_mode=? WHERE id=?",
                             (prepared.source_text, prepared.page_count, "visual" if prepared.image_data_url else "text", document_id))
                conn.execute("DELETE FROM document_pages WHERE document_id=?", (document_id,))
                for page_number, text in enumerate(prepared.page_texts, start=1):
                    insert(conn, "document_pages", document_id=document_id, page_number=page_number, text=text)
            async with asyncio.timeout(settings.ai_timeout_seconds):
                extraction = await app.state.document_extractor(app.state.client, settings, stored["type"], prepared, catalog, owner["timezone"])
            with connect(settings.database_path) as conn:
                conn.execute("BEGIN IMMEDIATE")
                approve_extraction(conn, document_id, extraction, prepared.page_texts, image=bool(prepared.image_data_url))
    except DocumentReadError as exc:
        mark_problem(settings.database_path, document_id, exc.code, exc.message, review=exc.needs_review)
    except ExtractionError as exc:
        mark_problem(settings.database_path, document_id, exc.code, exc.message)
    except (TimeoutError, asyncio.TimeoutError):
        mark_problem(settings.database_path, document_id, "extraction_timeout", "Document extraction exceeded the total time limit.")
    except DomainError as exc:
        mark_problem(settings.database_path, document_id, exc.code, exc.message)
    except (OSError, sqlite3.Error, ValueError, KeyError, TypeError):
        mark_problem(settings.database_path, document_id, "processing_failed", "The document could not be processed. Inspect its source and retry or submit a correction.")
    finally:
        app.state.active_documents.discard(document_id)


def queue_retry(app, document_id):
    if document_id in app.state.active_documents:
        raise DomainError("document_busy", "This document is already queued or processing.", 409)
    settings = app.state.settings
    with connect(settings.database_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT * FROM documents WHERE id=?", (document_id,)).fetchone()
        if not row:
            raise DomainError("document_not_found", "Document does not exist.", 404)
        if row["status"] == "completed":
            raise DomainError("document_already_approved", "Approved documents cannot be reprocessed into a second ledger entry.", 409)
        if not row["storage_path"]:
            raise DomainError("source_unavailable", "This record has no uploaded binary source to reprocess.", 409)
        stamp = now()
        conn.execute("UPDATE documents SET status='detected',error_code=NULL,error_message=NULL,updated_at=? WHERE id=?", (stamp, document_id))
        conn.execute("UPDATE processing_jobs SET status='failed',updated_at=? WHERE document_id=? AND status IN ('pending','processing')", (stamp, document_id))
        insert(conn, "processing_jobs", id=identifier("job"), document_id=document_id, kind="extract_document",
               status="pending", attempts=0, created_at=stamp, updated_at=stamp)
        return document_payload(conn.execute("SELECT * FROM documents WHERE id=?", (document_id,)).fetchone())


def review_document(app, document_id, extraction, note):
    if document_id in app.state.active_documents:
        raise DomainError("document_busy", "Wait for processing to finish before reviewing this document.", 409)
    with connect(app.state.database_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT * FROM documents WHERE id=?", (document_id,)).fetchone()
        if row is None:
            raise DomainError("document_not_found", "Document does not exist.", 404)
        if row["status"] == "completed":
            raise DomainError("document_already_approved", "This document is already approved; its ledger entry cannot be overwritten by review.", 409)
        pages = [p[0] for p in conn.execute("SELECT text FROM document_pages WHERE document_id=? ORDER BY page_number", (document_id,))]
        if not pages and row["evidence_mode"] != "visual":
            raise DomainError("source_unavailable", "Readable source evidence is unavailable. Upload a readable PDF or clear image first.", 409)
        return approve_extraction(conn, document_id, extraction, pages,
                                  image=row["evidence_mode"] == "visual", method="manual_review", review_note=note)
