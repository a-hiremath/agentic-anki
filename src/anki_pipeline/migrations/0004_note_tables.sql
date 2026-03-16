-- Migration 0004: Note candidates, synthesis attempts, validation results

CREATE TABLE IF NOT EXISTS synthesis_attempts (
    attempt_id        TEXT PRIMARY KEY,
    run_id            TEXT NOT NULL REFERENCES pipeline_runs(run_id),
    knowledge_item_id TEXT NOT NULL REFERENCES knowledge_items(item_id),
    prompt_version    TEXT NOT NULL DEFAULT '',
    model_name        TEXT NOT NULL DEFAULT '',
    notes_generated   INTEGER NOT NULL DEFAULT 0,
    notes_accepted    INTEGER NOT NULL DEFAULT 0,
    raw_response      TEXT NOT NULL DEFAULT '',
    error_message     TEXT,
    created_at        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS note_candidates (
    candidate_id        TEXT PRIMARY KEY,
    run_id              TEXT NOT NULL REFERENCES pipeline_runs(run_id),
    knowledge_item_id   TEXT NOT NULL REFERENCES knowledge_items(item_id),
    note_type           TEXT NOT NULL,
    front               TEXT,
    back                TEXT,
    text                TEXT,
    back_extra          TEXT,
    source_field        TEXT NOT NULL DEFAULT '',
    tags                TEXT NOT NULL DEFAULT '[]',
    note_identity_hash  TEXT NOT NULL DEFAULT '',
    provenance_kind     TEXT NOT NULL DEFAULT 'source_extracted',
    synthesis_attempt_id TEXT NOT NULL DEFAULT '',
    created_at          TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS validation_results (
    result_id     TEXT PRIMARY KEY,
    candidate_id  TEXT NOT NULL REFERENCES note_candidates(candidate_id),
    run_id        TEXT NOT NULL REFERENCES pipeline_runs(run_id),
    passed        INTEGER NOT NULL DEFAULT 0,
    failure_codes TEXT NOT NULL DEFAULT '[]',
    warning_codes TEXT NOT NULL DEFAULT '[]',
    created_at    TEXT NOT NULL
);

PRAGMA user_version = 4;
