PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS source_records (
    id TEXT PRIMARY KEY,
    source_type TEXT NOT NULL,
    source_path TEXT,
    content_hash TEXT,
    recorded_at TEXT,
    raw_payload TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS fact_records (
    id TEXT PRIMARY KEY,
    fact_type TEXT NOT NULL,
    source_id TEXT NOT NULL,
    recorded_at TEXT,
    payload TEXT NOT NULL,
    confidence REAL,
    is_verified INTEGER NOT NULL DEFAULT 0,
    verified_by TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (source_id) REFERENCES source_records(id)
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    action TEXT NOT NULL,
    before_value TEXT,
    after_value TEXT,
    actor TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS meal_records (
    fact_id TEXT PRIMARY KEY,
    calories_estimated REAL,
    calories_confirmed REAL,
    protein_estimated REAL,
    confirmation_status TEXT NOT NULL DEFAULT 'pending',
    confirmed_by TEXT,
    confirmed_at TEXT,
    FOREIGN KEY (fact_id) REFERENCES fact_records(id)
);

CREATE TABLE IF NOT EXISTS workout_records (
    fact_id TEXT PRIMARY KEY,
    duration_minutes REAL,
    calories_burned_estimated REAL,
    calories_burned_confirmed REAL,
    confirmation_status TEXT NOT NULL DEFAULT 'pending',
    confirmed_by TEXT,
    confirmed_at TEXT,
    FOREIGN KEY (fact_id) REFERENCES fact_records(id)
);

CREATE INDEX IF NOT EXISTS idx_fact_records_type_time
    ON fact_records(fact_type, recorded_at);
CREATE INDEX IF NOT EXISTS idx_fact_records_source
    ON fact_records(source_id);
