-- Migration 0001: Core tables (runs, sources, chunks, knowledge items, extraction)

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id           TEXT PRIMARY KEY,
    entry_mode       TEXT NOT NULL,
    deck_target      TEXT NOT NULL,
    status           TEXT NOT NULL DEFAULT 'running',
    trigger          TEXT NOT NULL DEFAULT 'manual',
    config_version   TEXT NOT NULL DEFAULT '',
    started_at       TEXT NOT NULL,
    finished_at      TEXT,
    error_message    TEXT,
    stages_completed TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS sources (
    source_id          TEXT PRIMARY KEY,
    run_id             TEXT NOT NULL REFERENCES pipeline_runs(run_id),
    entry_mode         TEXT NOT NULL,
    file_path          TEXT,
    media_type         TEXT NOT NULL DEFAULT 'text/plain',
    raw_file_hash      TEXT,
    source_fingerprint TEXT NOT NULL DEFAULT '',
    canonical_text     TEXT NOT NULL DEFAULT '',
    char_count         INTEGER NOT NULL DEFAULT 0,
    created_at         TEXT NOT NULL,
    UNIQUE(source_fingerprint)
);

CREATE TABLE IF NOT EXISTS chunks (
    chunk_id     TEXT PRIMARY KEY,
    source_id    TEXT NOT NULL REFERENCES sources(source_id),
    run_id       TEXT NOT NULL REFERENCES pipeline_runs(run_id),
    ordinal      INTEGER NOT NULL,
    char_start   INTEGER NOT NULL,
    char_end     INTEGER NOT NULL,
    text         TEXT NOT NULL,
    token_count  INTEGER NOT NULL DEFAULT 0,
    heading_path TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS knowledge_items (
    item_id          TEXT PRIMARY KEY,
    run_id           TEXT NOT NULL REFERENCES pipeline_runs(run_id),
    source_id        TEXT REFERENCES sources(source_id),
    chunk_id         TEXT REFERENCES chunks(chunk_id),
    item_type        TEXT NOT NULL,
    claim            TEXT NOT NULL,
    content_hash     TEXT NOT NULL DEFAULT '',
    deck_target      TEXT NOT NULL DEFAULT '',
    provenance_kind  TEXT NOT NULL DEFAULT 'source_extracted',
    subject_tag_root TEXT NOT NULL DEFAULT '',
    why_memorable    TEXT,
    is_active        INTEGER NOT NULL DEFAULT 1,
    is_duplicate     INTEGER NOT NULL DEFAULT 0,
    created_at       TEXT NOT NULL,
    UNIQUE(content_hash, deck_target, is_active)
);

CREATE TABLE IF NOT EXISTS extraction_attempts (
    attempt_id       TEXT PRIMARY KEY,
    run_id           TEXT NOT NULL REFERENCES pipeline_runs(run_id),
    chunk_id         TEXT NOT NULL REFERENCES chunks(chunk_id),
    prompt_version   TEXT NOT NULL DEFAULT '',
    model_name       TEXT NOT NULL DEFAULT '',
    items_extracted  INTEGER NOT NULL DEFAULT 0,
    items_accepted   INTEGER NOT NULL DEFAULT 0,
    items_duplicate  INTEGER NOT NULL DEFAULT 0,
    raw_response     TEXT NOT NULL DEFAULT '',
    error_message    TEXT,
    created_at       TEXT NOT NULL
);

PRAGMA user_version = 1;
