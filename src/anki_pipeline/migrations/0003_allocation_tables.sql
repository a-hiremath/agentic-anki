-- Migration 0003: Ranking assessments and selection decisions

CREATE TABLE IF NOT EXISTS ranking_assessments (
    ranking_id        TEXT PRIMARY KEY,
    run_id            TEXT NOT NULL REFERENCES pipeline_runs(run_id),
    knowledge_item_id TEXT NOT NULL REFERENCES knowledge_items(item_id),
    importance        REAL NOT NULL DEFAULT 0.0,
    forgettability    REAL NOT NULL DEFAULT 0.0,
    testability       REAL NOT NULL DEFAULT 0.0,
    aggregate_score   REAL NOT NULL DEFAULT 0.0,
    estimated_card_cost REAL NOT NULL DEFAULT 1.0,
    utility_density   REAL NOT NULL DEFAULT 0.0,
    prompt_version    TEXT NOT NULL DEFAULT '',
    model_name        TEXT NOT NULL DEFAULT '',
    created_at        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS selection_decisions (
    decision_id       TEXT PRIMARY KEY,
    run_id            TEXT NOT NULL REFERENCES pipeline_runs(run_id),
    knowledge_item_id TEXT NOT NULL REFERENCES knowledge_items(item_id),
    selected          INTEGER NOT NULL DEFAULT 0,
    reason            TEXT NOT NULL,
    budget_snapshot   TEXT NOT NULL DEFAULT '{}',
    created_at        TEXT NOT NULL
);

PRAGMA user_version = 3;
