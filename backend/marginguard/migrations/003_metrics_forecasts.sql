CREATE TABLE forecast_snapshots (
    run_id TEXT PRIMARY KEY REFERENCES forecast_runs(id),
    cache_key TEXT NOT NULL UNIQUE,
    as_of_date TEXT NOT NULL,
    response_json TEXT NOT NULL CHECK(json_valid(response_json))
);
CREATE INDEX forecast_snapshot_dates_idx ON forecast_snapshots(as_of_date);

CREATE TABLE coverage_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    channel_id TEXT NOT NULL REFERENCES channels(id),
    previous_status TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('complete','closed')),
    source_data_version INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
