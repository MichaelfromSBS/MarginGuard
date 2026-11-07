"""Explicit offline import of the approved synthetic v2 history; never a model call.

This is distinct from document extraction. It requires an empty business database,
uses the same business approval checks as uploads, and commits the corpus atomically.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import sqlite3

from pydantic import ValidationError

from backend.config import ROOT

from .db import MigrationError, connect, initialize_database
from .document_io import DocumentReadError, read_document
from .ingestion import approve_extraction, identifier, insert, now
from .schemas import Channel, Coverage, Ingredient, InvoiceExtraction, MenuPrice, ReceiptExtraction

DEFAULT_SOURCE = ROOT / "demo_data" / "demo_data_v2"
MAX_CORPUS_BYTES = 50 * 1024 * 1024
MAX_RECEIPTS = 20_000


def _text(path: Path, max_bytes: int = MAX_CORPUS_BYTES) -> str:
    data = path.read_bytes()
    if len(data) > max_bytes:
        raise ValueError(f"Fixture file exceeds the import limit: {path.name}")
    return data.decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")


def _csv(path: Path) -> list[dict]:
    # DictReader preserves quoted JSON aliases and comma-containing names.
    import io
    return list(csv.DictReader(io.StringIO(_text(path, 2 * 1024 * 1024))))


def _jsonl(path: Path) -> list[dict]:
    rows = []
    for line_number, line in enumerate(_text(path).splitlines(), start=1):
        if not line.strip():
            continue
        row = json.loads(line)
        if not isinstance(row, dict):
            raise ValueError(f"Expected a JSON object at {path.name}:{line_number}")
        rows.append(row)
        if len(rows) > MAX_RECEIPTS:
            raise ValueError("Fixture history exceeds 20,000 receipt records.")
    return rows


def _load_source(source: Path) -> dict:
    source = source.resolve()
    required = [
        *(source / "config" / name for name in ["ingredients.csv", "dishes.csv", "channels.csv", "menu_prices.csv", "recipes.csv", "vendors.csv", "calendar.csv", "demo_policy.json"]),
        source / "history" / "receipts.jsonl", source / "history" / "receipt_sources.jsonl",
        source / "history" / "coverage.csv",
    ]
    invoice_files = sorted((source / "history" / "invoices").glob("*.expected.json"))
    if not invoice_files or len(invoice_files) > 500:
        raise ValueError("History must contain between 1 and 500 expected invoice records.")
    for expected in invoice_files:
        stem = expected.name.removesuffix(".expected.json")
        required.extend([expected, expected.with_name(stem + ".txt"), expected.with_name(stem + ".pdf")])
    if any(not path.is_file() for path in required):
        raise ValueError("The fixture corpus is missing required config, history or paired source files.")
    if sum(path.stat().st_size for path in required) > MAX_CORPUS_BYTES:
        raise ValueError("The fixture corpus exceeds the 50 MB import limit.")
    fingerprint = hashlib.sha256()
    for path in sorted(required):
        fingerprint.update(path.relative_to(source).as_posix().encode("utf-8") + b"\0")
        content = path.read_bytes() if path.suffix == ".pdf" else _text(path).encode("utf-8")
        fingerprint.update(len(content).to_bytes(8, "big") + content)

    ingredients = []
    for row in _csv(source / "config/ingredients.csv"):
        ingredients.append(Ingredient(id=row["ingredient_id"], name=row["name"], base_unit=row["base_unit"], aliases=json.loads(row["aliases_json"])))
    dishes = _csv(source / "config/dishes.csv")
    channels = [Channel(id=r["channel_id"], name=r["name"], fee_rate=r["fee_rate"], packaging_cost=r["packaging_cost"]) for r in _csv(source / "config/channels.csv")]
    menu_prices = _csv(source / "config/menu_prices.csv")
    recipes = _csv(source / "config/recipes.csv")
    vendors = _csv(source / "config/vendors.csv")
    vendor_ids = {r["vendor_id"] for r in vendors}
    calendar = _csv(source / "config/calendar.csv")
    if any(row["open"] not in {"yes", "no"} for row in calendar):
        raise ValueError("Calendar open values must be yes or no.")

    invoices = []
    for path in invoice_files:
        extraction = InvoiceExtraction.model_validate_json(_text(path, 1024 * 1024))
        stem = path.name.removesuffix(".expected.json")
        text = _text(path.with_name(stem + ".txt"), 256 * 1024)
        pdf_path = path.with_name(stem + ".pdf")
        pdf_bytes = pdf_path.read_bytes()
        prepared = read_document(pdf_bytes, "application/pdf")
        if extraction.vendor_id not in vendor_ids:
            raise ValueError(f"Invoice supplier is not in the fixture catalog: {path.name}")
        if any(item.source_text not in text for item in extraction.items):
            raise ValueError(f"Invoice evidence is missing from paired text: {path.name}")
        # PDF exact-page evidence is independently checked again by the approval
        # validator; these are genuine source documents, not invented OCR outputs.
        invoices.append((extraction, pdf_path.name, pdf_bytes, prepared))

    sources = {}
    for row in _jsonl(source / "history/receipt_sources.jsonl"):
        number, text = row.get("receipt_number"), row.get("source_text")
        if not isinstance(number, str) or not isinstance(text, str) or not text.strip() or len(text) > 64000:
            raise ValueError("Receipt source entries require an ID and bounded literal source text.")
        if number in sources:
            raise ValueError("Duplicate receipt number in source text history.")
        sources[number] = text
    receipts = [ReceiptExtraction.model_validate(row) for row in _jsonl(source / "history/receipts.jsonl")]
    receipt_ids = [r.receipt_number for r in receipts]
    if not receipts or len(receipt_ids) != len(set(receipt_ids)) or set(receipt_ids) != set(sources):
        raise ValueError("Receipt records and literal sources must have matching unique IDs.")
    coverage = _csv(source / "history/coverage.csv")
    if len({(r["date"], r["channel_id"]) for r in coverage}) != len(coverage):
        raise ValueError("Coverage history contains duplicate date/channel rows.")
    return {
        "source": source, "fingerprint": fingerprint.hexdigest(), "ingredients": ingredients,
        "dishes": dishes, "channels": channels, "menu_prices": menu_prices,
        "recipes": recipes, "invoices": invoices, "receipts": receipts,
        "sources": sources, "coverage": coverage, "vendors": vendors, "calendar": calendar,
    }


def _assert_empty(conn):
    names = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    for name in names:
        if name in {"schema_migrations", "sqlite_sequence"}:
            continue
        quoted = '"' + name.replace('"', '""') + '"'
        if conn.execute(f"SELECT 1 FROM {quoted} LIMIT 1").fetchone():
            raise ValueError("Refusing to mix v2 history with existing business data. Choose a fresh database; no reset is performed.")


def _register(conn, kind: str, filename: str, data: bytes, source_text: str, pages: list[str]):
    stamp, doc_id = now(), identifier("fixture")
    insert(conn, "documents", id=doc_id, type=kind, filename=filename,
           sha256=hashlib.sha256(data).hexdigest(), media_type="application/pdf" if filename.endswith(".pdf") else "text/plain",
           status="detected", created_at=stamp, updated_at=stamp, is_demo=1,
           source_text=source_text, page_count=len(pages), evidence_mode="text",
           extraction_method="fixture_history")
    for index, text in enumerate(pages, start=1):
        insert(conn, "document_pages", document_id=doc_id, page_number=index, text=text)
    return doc_id


def _approve(conn, doc_id, extraction, pages):
    result = approve_extraction(conn, doc_id, extraction, pages, method="fixture_history")
    if result["status"] != "completed":
        raise ValueError(f"Historical fixture failed approval: {extraction.invoice_number if isinstance(extraction, InvoiceExtraction) else extraction.receipt_number}; review code {result['error_code']}.")


def import_demo(database: str | Path, source: str | Path = DEFAULT_SOURCE) -> dict:
    """Import a whole validated synthetic corpus atomically, or leave no ledger rows."""
    corpus = _load_source(Path(source))
    initialize_database(database)
    batch_id = "demo_v2_" + corpus["fingerprint"]
    with connect(database) as conn:
        conn.execute("BEGIN IMMEDIATE")
        marker = conn.execute("SELECT * FROM import_batches WHERE id=?", (batch_id,)).fetchone()
        if marker:
            owner = conn.execute("SELECT is_demo FROM restaurant WHERE id='tartan_burger_co'").fetchone()
            if owner is None or owner["is_demo"] != 1:
                raise ValueError("Import marker has no corresponding demo restaurant; review the database manually.")
            return {"imported": False, "source_fingerprint": corpus["fingerprint"], "invoice_count": marker["invoice_count"], "receipt_count": marker["receipt_count"]}
        _assert_empty(conn)
        insert(conn, "restaurant", id="tartan_burger_co", name="Tartan Burger Co.", currency="USD", timezone="America/New_York", data_version=0, is_demo=1)
        for vendor in corpus["vendors"]:
            insert(conn, "vendors", id=vendor["vendor_id"], name=vendor["name"], aliases_json="[]")
        for row in corpus["calendar"]:
            insert(conn, "restaurant_calendar", date=row["date"], is_open=int(row["open"] == "yes"), note=row.get("note", ""))
        for ingredient in corpus["ingredients"]:
            insert(conn, "ingredients", id=ingredient.id, name=ingredient.name, base_unit=ingredient.base_unit, aliases_json=json.dumps(ingredient.aliases))
        for dish in corpus["dishes"]:
            insert(conn, "dishes", id=dish["dish_id"], name=dish["name"])
        for channel in corpus["channels"]:
            insert(conn, "channels", **channel.model_dump())
        for row in corpus["menu_prices"]:
            item = MenuPrice(id=identifier("menu"), channel_id=row["channel_id"], price=row["price"], effective_date=row["effective_date"])
            insert(conn, "menu_prices", dish_id=row["dish_id"], **item.model_dump(mode="json"))
        versions = {}
        for row in corpus["recipes"]:
            if row["dish_id"] not in versions:
                versions[row["dish_id"]] = identifier("recipe")
                insert(conn, "recipe_versions", id=versions[row["dish_id"]], dish_id=row["dish_id"], effective_date="2026-09-01")
            insert(conn, "recipe_items", id=identifier("recipe_item"), recipe_version_id=versions[row["dish_id"]], ingredient_id=row["ingredient_id"], quantity=row["quantity"], unit=row["unit"])
        for extraction, filename, data, prepared in corpus["invoices"]:
            doc_id = _register(conn, "invoice", filename, data, prepared.source_text, prepared.page_texts)
            _approve(conn, doc_id, extraction, prepared.page_texts)
        for extraction in corpus["receipts"]:
            text = corpus["sources"][extraction.receipt_number]
            doc_id = _register(conn, "receipt", extraction.receipt_number + ".txt", text.encode("utf-8"), text, [text])
            _approve(conn, doc_id, extraction, [text])
        for row in corpus["coverage"]:
            item = Coverage(date=row["date"], channel_id=row["channel_id"], status=row["status"], updated_at=now())
            values = item.model_dump(mode="json")
            conn.execute("""INSERT INTO daily_coverage(date,channel_id,status,updated_at) VALUES (?,?,?,?)
                         ON CONFLICT(date,channel_id) DO UPDATE SET status=excluded.status,updated_at=excluded.updated_at""",
                         (values["date"], values["channel_id"], values["status"], values["updated_at"]))
        insert(conn, "import_batches", id=batch_id, source=str(corpus["source"]), created_at=now(), invoice_count=len(corpus["invoices"]), receipt_count=len(corpus["receipts"]))
    return {"imported": True, "source_fingerprint": corpus["fingerprint"], "invoice_count": len(corpus["invoices"]), "receipt_count": len(corpus["receipts"])}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Import explicitly fictional v2 history into a fresh database, with no AI calls.")
    parser.add_argument("--database", type=Path, required=True, help="Fresh SQLite file, e.g. data/demo-v2.db. Existing business data is never reset.")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE, help="v2 fixture corpus directory")
    args = parser.parse_args(argv)
    try:
        result = import_demo(args.database, args.source)
    except (OSError, ValueError, KeyError, sqlite3.Error, MigrationError, DocumentReadError, ValidationError) as exc:
        # Error text here is local operator feedback, never an HTTP provider payload.
        parser.error(str(exc))
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
