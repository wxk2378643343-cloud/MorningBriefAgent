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

CREATE TABLE IF NOT EXISTS todo_records (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    title TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    priority TEXT NOT NULL DEFAULT 'normal',
    due_date TEXT,
    feishu_task_id TEXT,
    completed_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (source_id) REFERENCES source_records(id)
);

CREATE TABLE IF NOT EXISTS schedule_records (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    title TEXT NOT NULL,
    start_at TEXT NOT NULL,
    end_at TEXT NOT NULL,
    feishu_event_id TEXT,
    sync_status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (source_id) REFERENCES source_records(id)
);

CREATE TABLE IF NOT EXISTS fund_records (
    id TEXT PRIMARY KEY,
    fund_code TEXT NOT NULL,
    fund_name TEXT,
    shares REAL,
    cost_price REAL,
    source_id TEXT,
    recorded_at TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (source_id) REFERENCES source_records(id)
);

CREATE TABLE IF NOT EXISTS fund_market_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fund_code TEXT NOT NULL,
    price REAL,
    change_percent REAL,
    market_time TEXT NOT NULL,
    data_source TEXT NOT NULL,
    is_realtime INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS news_items (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    title TEXT NOT NULL,
    url TEXT,
    published_at TEXT,
    category TEXT NOT NULL,
    summary TEXT,
    content_hash TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (source_id) REFERENCES source_records(id)
);

CREATE TABLE IF NOT EXISTS agent_usage_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id TEXT NOT NULL,
    task TEXT NOT NULL,
    provider TEXT NOT NULL,
    input_tokens INTEGER,
    output_tokens INTEGER,
    total_tokens INTEGER,
    token_source TEXT NOT NULL DEFAULT 'estimated',
    duration_ms INTEGER,
    status TEXT NOT NULL DEFAULT 'success',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS projection_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    projection_key TEXT NOT NULL,
    target_path TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_id TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'success',
    error_message TEXT,
    projected_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (projection_key, source_id)
);

CREATE TABLE IF NOT EXISTS data_sources (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    source_type TEXT NOT NULL,
    root_path TEXT NOT NULL UNIQUE,
    read_only INTEGER NOT NULL DEFAULT 1,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS file_records (
    id TEXT PRIMARY KEY,
    data_source_id TEXT NOT NULL,
    relative_path TEXT NOT NULL,
    file_name TEXT NOT NULL,
    file_type TEXT NOT NULL,
    size_bytes INTEGER NOT NULL DEFAULT 0,
    modified_at TEXT,
    content_hash TEXT,
    indexed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (data_source_id) REFERENCES data_sources(id),
    UNIQUE (data_source_id, relative_path)
);

CREATE TABLE IF NOT EXISTS file_recovery_operations (
    id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL,
    data_source_id TEXT NOT NULL,
    relative_path TEXT NOT NULL,
    recovery_path TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    error_message TEXT,
    deleted_at TEXT,
    restored_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (data_source_id) REFERENCES data_sources(id),
    UNIQUE (data_source_id, request_id)
);

CREATE TABLE IF NOT EXISTS installation_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    setup_version INTEGER NOT NULL DEFAULT 1,
    completed INTEGER NOT NULL DEFAULT 0,
    selected_provider TEXT,
    selected_channel TEXT,
    workspace_root TEXT,
    completed_at TEXT,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS local_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    is_secret INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS onboarding_steps (
    step_key TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'pending',
    detail TEXT,
    completed_at TEXT,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS workflow_runs (
    id TEXT PRIMARY KEY,
    workflow_key TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TEXT,
    exit_code INTEGER,
    log_path TEXT,
    error_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_fact_records_type_time
    ON fact_records(fact_type, recorded_at);
CREATE INDEX IF NOT EXISTS idx_fact_records_source
    ON fact_records(source_id);
CREATE INDEX IF NOT EXISTS idx_todo_records_status_due
    ON todo_records(status, due_date);
CREATE INDEX IF NOT EXISTS idx_schedule_records_time
    ON schedule_records(start_at, end_at);
CREATE INDEX IF NOT EXISTS idx_fund_snapshots_code_time
    ON fund_market_snapshots(fund_code, market_time);
CREATE INDEX IF NOT EXISTS idx_news_items_published
    ON news_items(published_at);
CREATE INDEX IF NOT EXISTS idx_agent_usage_created
    ON agent_usage_records(created_at);
CREATE INDEX IF NOT EXISTS idx_projection_records_source
    ON projection_records(source_type, source_id);
CREATE INDEX IF NOT EXISTS idx_file_records_source_path
    ON file_records(data_source_id, relative_path);
CREATE INDEX IF NOT EXISTS idx_file_records_type_modified
    ON file_records(file_type, modified_at);
CREATE INDEX IF NOT EXISTS idx_file_recovery_source_status
    ON file_recovery_operations(data_source_id, status, created_at);
