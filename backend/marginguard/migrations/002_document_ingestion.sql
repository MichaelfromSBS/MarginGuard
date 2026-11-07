ALTER TABLE documents ADD COLUMN storage_path TEXT;
ALTER TABLE documents ADD COLUMN page_count INTEGER;
ALTER TABLE documents ADD COLUMN evidence_mode TEXT NOT NULL DEFAULT 'text';
ALTER TABLE documents ADD COLUMN extraction_method TEXT;
ALTER TABLE documents ADD COLUMN extraction_json TEXT;
ALTER TABLE documents ADD COLUMN validation_issues_json TEXT NOT NULL DEFAULT '[]';
ALTER TABLE documents ADD COLUMN reviewed_at TEXT;
ALTER TABLE documents ADD COLUMN review_note TEXT;

CREATE TABLE document_pages (
    document_id TEXT NOT NULL REFERENCES documents(id),
    page_number INTEGER NOT NULL CHECK(page_number > 0),
    text TEXT NOT NULL,
    PRIMARY KEY(document_id, page_number)
);

CREATE TABLE review_events (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(id),
    created_at TEXT NOT NULL,
    note TEXT NOT NULL,
    extraction_json TEXT NOT NULL CHECK(json_valid(extraction_json)),
    outcome TEXT NOT NULL
);

CREATE TABLE data_changes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_data_version INTEGER NOT NULL,
    document_id TEXT NOT NULL REFERENCES documents(id),
    change_type TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE import_batches (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    created_at TEXT NOT NULL,
    invoice_count INTEGER NOT NULL,
    receipt_count INTEGER NOT NULL
);

CREATE INDEX review_documents_idx ON documents(status, updated_at);
CREATE UNIQUE INDEX invoices_normalized_key ON invoices(lower(trim(vendor_id)), lower(trim(invoice_number)));
CREATE UNIQUE INDEX receipts_normalized_key ON receipts(COALESCE(channel_id, ''), lower(trim(receipt_number)));

CREATE TABLE vendors (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    aliases_json TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(aliases_json))
);
INSERT INTO vendors(id,name) SELECT vendor_id,MIN(vendor_name) FROM invoices GROUP BY vendor_id;

CREATE TABLE restaurant_calendar (
    date TEXT PRIMARY KEY,
    is_open INTEGER NOT NULL CHECK(is_open IN (0,1)),
    note TEXT NOT NULL DEFAULT ''
);
