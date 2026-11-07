ALTER TABLE processing_jobs ADD COLUMN lease_owner TEXT;
ALTER TABLE processing_jobs ADD COLUMN lease_until TEXT;
ALTER TABLE processing_jobs ADD COLUMN available_at TEXT;
CREATE INDEX extraction_queue_idx ON processing_jobs(kind,status,available_at,created_at);

CREATE TABLE worker_leases (
    name TEXT PRIMARY KEY,
    owner TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    heartbeat_at TEXT NOT NULL,
    status TEXT NOT NULL,
    error_code TEXT
);
CREATE TABLE worker_state (key TEXT PRIMARY KEY,value TEXT NOT NULL);
CREATE TABLE watched_files (
    path TEXT PRIMARY KEY,
    size INTEGER NOT NULL,
    mtime_ns INTEGER NOT NULL,
    observed_at TEXT NOT NULL,
    document_id TEXT REFERENCES documents(id),
    error_code TEXT,
    processed INTEGER NOT NULL DEFAULT 0
);

ALTER TABLE alerts ADD COLUMN finding_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(finding_json));
ALTER TABLE alerts ADD COLUMN fingerprint TEXT NOT NULL DEFAULT '';
ALTER TABLE alerts ADD COLUMN revision INTEGER NOT NULL DEFAULT 1;
ALTER TABLE alerts ADD COLUMN suggestion TEXT NOT NULL DEFAULT '';
ALTER TABLE alerts ADD COLUMN explanation_status TEXT NOT NULL DEFAULT 'pending';
ALTER TABLE alerts ADD COLUMN calculation_version TEXT NOT NULL DEFAULT 'detectors_v1';

