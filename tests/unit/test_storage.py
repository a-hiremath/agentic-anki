"""Tests for storage layer: migrations, CRUD, FK enforcement (Spec Section 10)."""

import pytest
from pathlib import Path

from anki_pipeline.enums import (
    AssessmentLabel, EntryMode, KnowledgeItemType, ProvenanceKind, RunStatus, SelectionReason
)
from anki_pipeline.identity import generate_id
from anki_pipeline.models import (
    Chunk, GroundingAssessment, KnowledgeItem, PipelineRun, SourceRecord, SelectionDecision
)
from anki_pipeline.storage import (
    ChunkRepo, Database, GroundingAssessmentRepo, KnowledgeItemRepo,
    RunRepo, SelectionDecisionRepo, SourceRepo
)


def make_run(db: Database) -> PipelineRun:
    run = PipelineRun(
        run_id=generate_id(),
        entry_mode=EntryMode.document,
        deck_target="Math::Calc",
    )
    with db.connect() as conn:
        RunRepo.insert(conn, run)
    return run


def make_source(db: Database, run: PipelineRun) -> SourceRecord:
    source = SourceRecord(
        source_id=generate_id(),
        run_id=run.run_id,
        entry_mode=EntryMode.document,
        canonical_text="Some content here.",
        source_fingerprint=generate_id(),  # unique per test
        char_count=18,
    )
    with db.connect() as conn:
        SourceRepo.insert(conn, source)
    return source


class TestMigrations:
    def test_all_migrations_run(self, tmp_db: Database):
        with tmp_db.connect() as conn:
            version = conn.execute("PRAGMA user_version").fetchone()[0]
        assert version == 5  # all 5 migrations ran

    def test_tables_exist(self, tmp_db: Database):
        expected_tables = {
            "pipeline_runs", "sources", "chunks", "knowledge_items",
            "extraction_attempts", "grounding_assessments", "evidence_spans",
            "ranking_assessments", "selection_decisions", "synthesis_attempts",
            "note_candidates", "validation_results", "review_actions",
            "reviewed_notes", "export_records",
        }
        with tmp_db.connect() as conn:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        actual = {r["name"] for r in rows}
        assert expected_tables <= actual


class TestRunRepo:
    def test_insert_and_retrieve(self, tmp_db: Database):
        run = make_run(tmp_db)
        with tmp_db.connect() as conn:
            retrieved = RunRepo.get_by_id(conn, run.run_id)
        assert retrieved is not None
        assert retrieved.run_id == run.run_id
        assert retrieved.deck_target == "Math::Calc"

    def test_update_status(self, tmp_db: Database):
        run = make_run(tmp_db)
        with tmp_db.connect() as conn:
            RunRepo.update_status(conn, run.run_id, "completed", finished_at="2024-01-01T00:00:00")
            updated = RunRepo.get_by_id(conn, run.run_id)
        assert updated.status == RunStatus.completed

    def test_not_found_returns_none(self, tmp_db: Database):
        with tmp_db.connect() as conn:
            result = RunRepo.get_by_id(conn, "nonexistent")
        assert result is None


class TestSourceRepo:
    def test_insert_and_get_by_fingerprint(self, tmp_db: Database):
        run = make_run(tmp_db)
        source = make_source(tmp_db, run)

        with tmp_db.connect() as conn:
            retrieved = SourceRepo.get_by_fingerprint(conn, source.source_fingerprint)
        assert retrieved is not None
        assert retrieved.source_id == source.source_id

    def test_unique_fingerprint_constraint(self, tmp_db: Database):
        run = make_run(tmp_db)
        fp = generate_id()
        s1 = SourceRecord(
            source_id=generate_id(), run_id=run.run_id,
            entry_mode=EntryMode.document, source_fingerprint=fp,
        )
        s2 = SourceRecord(
            source_id=generate_id(), run_id=run.run_id,
            entry_mode=EntryMode.document, source_fingerprint=fp,  # same fingerprint
        )
        with tmp_db.connect() as conn:
            SourceRepo.insert(conn, s1)
        with pytest.raises(Exception):  # UNIQUE constraint
            with tmp_db.connect() as conn:
                SourceRepo.insert(conn, s2)


class TestChunkRepo:
    def test_insert_batch_and_retrieve(self, tmp_db: Database):
        run = make_run(tmp_db)
        source = make_source(tmp_db, run)
        chunks = [
            Chunk(
                chunk_id=generate_id(),
                source_id=source.source_id,
                run_id=run.run_id,
                ordinal=i,
                char_start=i * 50,
                char_end=(i + 1) * 50,
                text=f"chunk {i} text " * 3,
            )
            for i in range(3)
        ]
        with tmp_db.connect() as conn:
            ChunkRepo.insert_batch(conn, chunks)
            retrieved = ChunkRepo.get_by_source(conn, source.source_id)

        assert len(retrieved) == 3
        assert [c.ordinal for c in retrieved] == [0, 1, 2]


class TestKnowledgeItemRepo:
    def test_insert_and_get_by_hash(self, tmp_db: Database):
        run = make_run(tmp_db)
        source = make_source(tmp_db, run)

        item = KnowledgeItem(
            item_id=generate_id(),
            run_id=run.run_id,
            source_id=source.source_id,
            item_type=KnowledgeItemType.definition,
            claim="A set is a collection.",
            content_hash="abc123",
            deck_target="Math",
        )
        with tmp_db.connect() as conn:
            KnowledgeItemRepo.insert(conn, item)
            found = KnowledgeItemRepo.get_by_content_hash_and_deck(conn, "abc123", "Math")

        assert found is not None
        assert found.item_id == item.item_id

    def test_unique_constraint_content_hash_deck(self, tmp_db: Database):
        run = make_run(tmp_db)
        source = make_source(tmp_db, run)

        def make_item():
            return KnowledgeItem(
                item_id=generate_id(),
                run_id=run.run_id,
                source_id=source.source_id,
                item_type=KnowledgeItemType.definition,
                claim="Same claim.",
                content_hash="same_hash",
                deck_target="Math",
            )

        with tmp_db.connect() as conn:
            KnowledgeItemRepo.insert(conn, make_item())
        with pytest.raises(Exception):
            with tmp_db.connect() as conn:
                KnowledgeItemRepo.insert(conn, make_item())

    def test_fk_enforcement(self, tmp_db: Database):
        """Inserting an item with nonexistent run_id should fail."""
        item = KnowledgeItem(
            item_id=generate_id(),
            run_id="nonexistent_run",
            item_type=KnowledgeItemType.definition,
            claim="Some claim.",
            content_hash="xyz",
            deck_target="Math",
        )
        with pytest.raises(Exception):
            with tmp_db.connect() as conn:
                KnowledgeItemRepo.insert(conn, item)
