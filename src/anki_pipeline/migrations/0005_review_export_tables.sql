-- Migration 0005: Review actions, reviewed notes, export records

CREATE TABLE IF NOT EXISTS review_actions (
    action_id        TEXT PRIMARY KEY,
    run_id           TEXT NOT NULL REFERENCES pipeline_runs(run_id),
    candidate_id     TEXT NOT NULL REFERENCES note_candidates(candidate_id),
    decision         TEXT NOT NULL,
    edit_type        TEXT,
    edited_fields    TEXT NOT NULL DEFAULT '{}',
    reject_reason_code TEXT,
    reviewer_notes   TEXT,
    created_at       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reviewed_notes (
    reviewed_note_id  TEXT PRIMARY KEY,
    run_id            TEXT NOT NULL REFERENCES pipeline_runs(run_id),
    candidate_id      TEXT NOT NULL REFERENCES note_candidates(candidate_id),
    action_id         TEXT NOT NULL REFERENCES review_actions(action_id),
    note_type         TEXT NOT NULL,
    front             TEXT,
    back              TEXT,
    text              TEXT,
    back_extra        TEXT,
    source_field      TEXT NOT NULL DEFAULT '',
    tags              TEXT NOT NULL DEFAULT '[]',
    note_identity_hash TEXT NOT NULL DEFAULT '',
    provenance_kind   TEXT NOT NULL DEFAULT 'source_extracted',
    ready_for_export  INTEGER NOT NULL DEFAULT 1,
    created_at        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS export_records (
    export_id         TEXT PRIMARY KEY,
    reviewed_note_id  TEXT NOT NULL,
    run_id            TEXT NOT NULL,
    deck_target       TEXT NOT NULL,
    tsv_row           TEXT NOT NULL DEFAULT '',
    export_method     TEXT NOT NULL DEFAULT 'tsv',
    status            TEXT NOT NULL DEFAULT 'success',
    output_file       TEXT NOT NULL DEFAULT '',
    created_at        TEXT NOT NULL
);

PRAGMA user_version = 5;
