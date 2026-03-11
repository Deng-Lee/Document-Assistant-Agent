from __future__ import annotations


DOCUMENTS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS documents (
    doc_id TEXT PRIMARY KEY,
    doc_type TEXT NOT NULL,
    title TEXT NOT NULL,
    latest_version_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    status TEXT NOT NULL
);
"""


DOC_VERSIONS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS doc_versions (
    doc_version_id TEXT PRIMARY KEY,
    doc_id TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    ingest_time TEXT NOT NULL,
    source_path TEXT,
    size_bytes INTEGER,
    FOREIGN KEY (doc_id) REFERENCES documents(doc_id)
);
"""


CHUNKS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS chunks (
    chunk_id TEXT PRIMARY KEY,
    doc_id TEXT NOT NULL,
    doc_version_id TEXT NOT NULL,
    doc_type TEXT NOT NULL,
    chunk_type TEXT NOT NULL,
    record_date TEXT,
    position TEXT,
    orientation TEXT,
    distance TEXT,
    goal TEXT,
    opponent_control TEXT,
    heading_path_json TEXT NOT NULL,
    locator_json TEXT NOT NULL,
    metadata_digest_json TEXT NOT NULL,
    safe_summary TEXT,
    summary_model TEXT,
    summary_prompt_version TEXT,
    summary_status TEXT,
    summary_error_code TEXT,
    summary_retry_count INTEGER,
    summary_last_attempt_at TEXT,
    summary_next_retry_at TEXT,
    summary_last_error_at TEXT,
    clean_search_text TEXT,
    clean_embed_text TEXT,
    raw_text_ref TEXT,
    FOREIGN KEY (doc_id) REFERENCES documents(doc_id),
    FOREIGN KEY (doc_version_id) REFERENCES doc_versions(doc_version_id)
);
"""


CHUNK_FTS_TABLE_SQL = """
CREATE VIRTUAL TABLE IF NOT EXISTS chunk_fts USING fts5(
    chunk_id UNINDEXED,
    doc_type UNINDEXED,
    clean_search_text,
    content='',
    tokenize='unicode61'
);
"""


TRACES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS traces (
    trace_id TEXT PRIMARY KEY,
    conversation_id TEXT,
    runtime_config_snapshot_json TEXT NOT NULL,
    request_log_json TEXT NOT NULL,
    retrieval_log_json TEXT NOT NULL,
    evidence_log_json TEXT NOT NULL,
    generation_log_json TEXT NOT NULL,
    spans_json TEXT NOT NULL,
    events_json TEXT NOT NULL
);
"""


GOLDEN_CASES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS golden_cases (
    case_id TEXT PRIMARY KEY,
    query TEXT NOT NULL,
    domain TEXT NOT NULL,
    trace_id TEXT,
    expected_behavior_json TEXT NOT NULL,
    expected_chunk_ids_json TEXT NOT NULL
);
"""


EVAL_RUNS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS eval_runs (
    eval_run_id TEXT PRIMARY KEY,
    eval_set_id TEXT NOT NULL,
    model_variant TEXT NOT NULL,
    created_at TEXT NOT NULL,
    metrics_json TEXT NOT NULL,
    failures_json TEXT NOT NULL,
    result_json TEXT
);
"""


EVAL_RUBRICS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS eval_rubrics (
    rubric_id TEXT PRIMARY KEY,
    eval_run_id TEXT NOT NULL,
    trace_id TEXT NOT NULL,
    reviewer TEXT NOT NULL,
    scores_json TEXT NOT NULL,
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


PROFILES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS profiles (
    profile_version_id TEXT PRIMARY KEY,
    profile_summary_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


JOBS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS jobs (
    job_id TEXT PRIMARY KEY,
    job_type TEXT NOT NULL,
    status TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    error_message TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


ALL_SQLITE_STATEMENTS = [
    DOCUMENTS_TABLE_SQL,
    DOC_VERSIONS_TABLE_SQL,
    CHUNKS_TABLE_SQL,
    CHUNK_FTS_TABLE_SQL,
    TRACES_TABLE_SQL,
    GOLDEN_CASES_TABLE_SQL,
    EVAL_RUNS_TABLE_SQL,
    EVAL_RUBRICS_TABLE_SQL,
    PROFILES_TABLE_SQL,
    JOBS_TABLE_SQL,
]
