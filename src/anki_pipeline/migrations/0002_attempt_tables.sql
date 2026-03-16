-- Migration 0002: Grounding assessments and evidence spans

CREATE TABLE IF NOT EXISTS evidence_spans (
    span_id           TEXT PRIMARY KEY,
    knowledge_item_id TEXT NOT NULL REFERENCES knowledge_items(item_id),
    chunk_id          TEXT NOT NULL REFERENCES chunks(chunk_id),
    char_start        INTEGER NOT NULL,
    char_end          INTEGER NOT NULL,
    text              TEXT NOT NULL,
    page_or_section   TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS grounding_assessments (
    assessment_id     TEXT PRIMARY KEY,
    run_id            TEXT NOT NULL REFERENCES pipeline_runs(run_id),
    knowledge_item_id TEXT NOT NULL REFERENCES knowledge_items(item_id),
    chunk_id          TEXT REFERENCES chunks(chunk_id),
    label             TEXT NOT NULL,
    score             REAL,
    prompt_version    TEXT NOT NULL DEFAULT '',
    model_name        TEXT NOT NULL DEFAULT '',
    created_at        TEXT NOT NULL
);

PRAGMA user_version = 2;
