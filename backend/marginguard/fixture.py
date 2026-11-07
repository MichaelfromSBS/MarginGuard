"""Explicit offline demo ingestion. Never used automatically by the HTTP API."""
import argparse
import json
import mimetypes
from pathlib import Path

from backend.config import Settings
from .db import connect, initialize_database
from .document_io import read_document, DocumentReadError
from .errors import DomainError
from .ingestion import approve_extraction, document_payload, insert, register_upload, restaurant_record
from .schemas import InvoiceExtraction, ReceiptExtraction


def ingest_fixture(settings, path: Path, expected: Path, document_type: str):
    initialize_database(settings.database_path)
    with connect(settings.database_path) as conn:
        if not restaurant_record(conn)["is_demo"]:
            raise DomainError("fixture_mode_forbidden", "Expected-output fixtures may only be loaded into an explicitly fictional demo restaurant.", 409)
    model = InvoiceExtraction if document_type == "invoice" else ReceiptExtraction
    extraction = model.model_validate_json(expected.read_text(encoding="utf-8"))
    data = path.read_bytes()
    media = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    prepared = read_document(data, media)
    registered, duplicate = register_upload(settings, document_type, path.name, media, data)
    with connect(settings.database_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT * FROM documents WHERE id=?", (registered["id"],)).fetchone()
        if row["status"] == "completed":
            return {"duplicate": True, "document": document_payload(row, detail=True)}
        if row["status"] == "processing":
            raise DomainError("document_busy", "A live extraction is already processing these bytes.", 409)
        conn.execute("UPDATE documents SET source_text=?,page_count=?,evidence_mode=? WHERE id=?",
                     (prepared.source_text, prepared.page_count, "visual" if prepared.image_data_url else "text", registered["id"]))
        conn.execute("DELETE FROM document_pages WHERE document_id=?", (registered["id"],))
        for number, text in enumerate(prepared.page_texts, start=1):
            insert(conn, "document_pages", document_id=registered["id"], page_number=number, text=text)
        result = approve_extraction(conn, registered["id"], extraction, prepared.page_texts,
                                    image=bool(prepared.image_data_url), method="fixture_expected")
        return {"duplicate": duplicate, "document": result}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Validate explicitly supplied expected JSON in a fictional demo database. No model is called.")
    parser.add_argument("--file", type=Path, required=True)
    parser.add_argument("--expected", type=Path, required=True)
    parser.add_argument("--type", choices=["invoice", "receipt"], required=True)
    parser.add_argument("--database", type=Path)
    args = parser.parse_args(argv)
    settings = Settings(**({"database_path": args.database} if args.database else {}))
    try:
        result = ingest_fixture(settings, args.file, args.expected, args.type)
    except (DomainError, DocumentReadError, ValueError, OSError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
