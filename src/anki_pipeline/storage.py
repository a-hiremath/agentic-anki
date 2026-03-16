"""Database class, migration runner, and repository classes (Spec Section 10)."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from importlib import resources
from pathlib import Path
from typing import Generator

from anki_pipeline.models import (
    Chunk,
    ExportRecord,
    ExtractionAttempt,
    GroundingAssessment,
    KnowledgeItem,
    NoteCandidate,
    PipelineRun,
    RankingAssessment,
    ReviewAction,
    ReviewedNote,
    SelectionDecision,
    SourceRecord,
    SynthesisAttempt,
    ValidationResult,
    EvidenceSpan,
)

# Path to the migrations directory (sibling of this file)
_MIGRATIONS_DIR = Path(__file__).parent / "migrations"


class Database:
    """SQLite database with migration support.

    Usage::

        db = Database(Path("pipeline.db"))
        with db.connect() as conn:
            RunRepo.insert(conn, run)
    """

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        # Run migrations immediately on construction
        with self._raw_connect() as conn:
            self._configure(conn)
            self._run_migrations(conn)

    def _raw_connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _configure(self, conn: sqlite3.Connection) -> None:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")

    @contextmanager
    def connect(self) -> Generator[sqlite3.Connection, None, None]:
        """Yield a connection; auto-commit on success, rollback on exception."""
        conn = self._raw_connect()
        self._configure(conn)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _run_migrations(self, conn: sqlite3.Connection) -> None:
        """Apply numbered .sql migration files that are newer than the current user_version."""
        current_version = conn.execute("PRAGMA user_version").fetchone()[0]

        migration_files = sorted(_MIGRATIONS_DIR.glob("*.sql"))
        for migration_path in migration_files:
            # File names: 0001_init.sql  → version 1
            stem = migration_path.stem.split("_")[0]
            file_version = int(stem)
            if file_version <= current_version:
                continue
            sql = migration_path.read_text(encoding="utf-8")
            # Execute each statement separately (sqlite3 doesn't support multi-statement)
            # But PRAGMA user_version must be set via executescript or pragma
            conn.executescript(sql)

        conn.commit()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _dt(value: object) -> str:
    """Convert datetime or str to ISO-8601 string."""
    if value is None:
        return ""
    return str(value)


def _json(value: object) -> str:
    return json.dumps(value)


def _from_json(value: str | None) -> object:
    if not value:
        return []
    return json.loads(value)


# ---------------------------------------------------------------------------
# RunRepo
# ---------------------------------------------------------------------------

class RunRepo:
    @staticmethod
    def insert(conn: sqlite3.Connection, run: PipelineRun) -> None:
        conn.execute(
            """
            INSERT INTO pipeline_runs
                (run_id, entry_mode, deck_target, status, trigger, config_version,
                 started_at, finished_at, error_message, stages_completed)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run.run_id,
                run.entry_mode.value,
                run.deck_target,
                run.status.value,
                run.trigger,
                run.config_version,
                _dt(run.started_at),
                _dt(run.finished_at),
                run.error_message,
                _json(run.stages_completed),
            ),
        )

    @staticmethod
    def update_status(
        conn: sqlite3.Connection,
        run_id: str,
        status: str,
        finished_at: str | None = None,
        error_message: str | None = None,
        stages_completed: list[str] | None = None,
    ) -> None:
        parts = ["status = ?"]
        args: list[object] = [status]
        if finished_at is not None:
            parts.append("finished_at = ?")
            args.append(finished_at)
        if error_message is not None:
            parts.append("error_message = ?")
            args.append(error_message)
        if stages_completed is not None:
            parts.append("stages_completed = ?")
            args.append(_json(stages_completed))
        args.append(run_id)
        conn.execute(f"UPDATE pipeline_runs SET {', '.join(parts)} WHERE run_id = ?", args)

    @staticmethod
    def get_by_id(conn: sqlite3.Connection, run_id: str) -> PipelineRun | None:
        row = conn.execute(
            "SELECT * FROM pipeline_runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        if row is None:
            return None
        from anki_pipeline.enums import EntryMode, RunStatus
        return PipelineRun(
            run_id=row["run_id"],
            entry_mode=EntryMode(row["entry_mode"]),
            deck_target=row["deck_target"],
            status=RunStatus(row["status"]),
            trigger=row["trigger"],
            config_version=row["config_version"],
            started_at=row["started_at"],
            finished_at=row["finished_at"] or None,
            error_message=row["error_message"],
            stages_completed=json.loads(row["stages_completed"] or "[]"),
        )


# ---------------------------------------------------------------------------
# SourceRepo
# ---------------------------------------------------------------------------

class SourceRepo:
    @staticmethod
    def insert(conn: sqlite3.Connection, source: SourceRecord) -> None:
        conn.execute(
            """
            INSERT INTO sources
                (source_id, run_id, entry_mode, file_path, media_type, raw_file_hash,
                 source_fingerprint, canonical_text, char_count, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                source.source_id,
                source.run_id,
                source.entry_mode.value,
                source.file_path,
                source.media_type,
                source.raw_file_hash,
                source.source_fingerprint,
                source.canonical_text,
                source.char_count,
                _dt(source.created_at),
            ),
        )

    @staticmethod
    def get_by_fingerprint(conn: sqlite3.Connection, fingerprint: str) -> SourceRecord | None:
        row = conn.execute(
            "SELECT * FROM sources WHERE source_fingerprint = ?", (fingerprint,)
        ).fetchone()
        if row is None:
            return None
        from anki_pipeline.enums import EntryMode
        return SourceRecord(
            source_id=row["source_id"],
            run_id=row["run_id"],
            entry_mode=EntryMode(row["entry_mode"]),
            file_path=row["file_path"],
            media_type=row["media_type"],
            raw_file_hash=row["raw_file_hash"],
            source_fingerprint=row["source_fingerprint"],
            canonical_text=row["canonical_text"],
            char_count=row["char_count"],
            created_at=row["created_at"],
        )

    @staticmethod
    def get_by_id(conn: sqlite3.Connection, source_id: str) -> SourceRecord | None:
        row = conn.execute(
            "SELECT * FROM sources WHERE source_id = ?", (source_id,)
        ).fetchone()
        if row is None:
            return None
        from anki_pipeline.enums import EntryMode
        return SourceRecord(
            source_id=row["source_id"],
            run_id=row["run_id"],
            entry_mode=EntryMode(row["entry_mode"]),
            file_path=row["file_path"],
            media_type=row["media_type"],
            raw_file_hash=row["raw_file_hash"],
            source_fingerprint=row["source_fingerprint"],
            canonical_text=row["canonical_text"],
            char_count=row["char_count"],
            created_at=row["created_at"],
        )


# ---------------------------------------------------------------------------
# ChunkRepo
# ---------------------------------------------------------------------------

class ChunkRepo:
    @staticmethod
    def insert_batch(conn: sqlite3.Connection, chunks: list[Chunk]) -> None:
        conn.executemany(
            """
            INSERT INTO chunks
                (chunk_id, source_id, run_id, ordinal, char_start, char_end,
                 text, token_count, heading_path)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    c.chunk_id,
                    c.source_id,
                    c.run_id,
                    c.ordinal,
                    c.char_start,
                    c.char_end,
                    c.text,
                    c.token_count,
                    c.heading_path,
                )
                for c in chunks
            ],
        )

    @staticmethod
    def get_by_source(conn: sqlite3.Connection, source_id: str) -> list[Chunk]:
        rows = conn.execute(
            "SELECT * FROM chunks WHERE source_id = ? ORDER BY ordinal", (source_id,)
        ).fetchall()
        return [
            Chunk(
                chunk_id=r["chunk_id"],
                source_id=r["source_id"],
                run_id=r["run_id"],
                ordinal=r["ordinal"],
                char_start=r["char_start"],
                char_end=r["char_end"],
                text=r["text"],
                token_count=r["token_count"],
                heading_path=r["heading_path"],
            )
            for r in rows
        ]


# ---------------------------------------------------------------------------
# KnowledgeItemRepo
# ---------------------------------------------------------------------------

class KnowledgeItemRepo:
    @staticmethod
    def insert(conn: sqlite3.Connection, item: KnowledgeItem) -> None:
        conn.execute(
            """
            INSERT INTO knowledge_items
                (item_id, run_id, source_id, chunk_id, item_type, claim, content_hash,
                 deck_target, provenance_kind, subject_tag_root, why_memorable,
                 is_active, is_duplicate, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item.item_id,
                item.run_id,
                item.source_id,
                item.chunk_id,
                item.item_type.value,
                item.claim,
                item.content_hash,
                item.deck_target,
                item.provenance_kind.value,
                item.subject_tag_root,
                item.why_memorable,
                int(item.is_active),
                int(item.is_duplicate),
                _dt(item.created_at),
            ),
        )

    @staticmethod
    def get_by_content_hash_and_deck(
        conn: sqlite3.Connection, content_hash: str, deck_target: str
    ) -> KnowledgeItem | None:
        row = conn.execute(
            "SELECT * FROM knowledge_items WHERE content_hash = ? AND deck_target = ? AND is_active = 1",
            (content_hash, deck_target),
        ).fetchone()
        if row is None:
            return None
        return KnowledgeItemRepo._row_to_model(row)

    @staticmethod
    def get_active_by_source(conn: sqlite3.Connection, source_id: str) -> list[KnowledgeItem]:
        rows = conn.execute(
            "SELECT * FROM knowledge_items WHERE source_id = ? AND is_active = 1",
            (source_id,),
        ).fetchall()
        return [KnowledgeItemRepo._row_to_model(r) for r in rows]

    @staticmethod
    def get_by_id(conn: sqlite3.Connection, item_id: str) -> KnowledgeItem | None:
        row = conn.execute(
            "SELECT * FROM knowledge_items WHERE item_id = ?", (item_id,)
        ).fetchone()
        if row is None:
            return None
        return KnowledgeItemRepo._row_to_model(row)

    @staticmethod
    def _row_to_model(row: sqlite3.Row) -> KnowledgeItem:
        from anki_pipeline.enums import KnowledgeItemType, ProvenanceKind
        return KnowledgeItem(
            item_id=row["item_id"],
            run_id=row["run_id"],
            source_id=row["source_id"],
            chunk_id=row["chunk_id"],
            item_type=KnowledgeItemType(row["item_type"]),
            claim=row["claim"],
            content_hash=row["content_hash"],
            deck_target=row["deck_target"],
            provenance_kind=ProvenanceKind(row["provenance_kind"]),
            subject_tag_root=row["subject_tag_root"],
            why_memorable=row["why_memorable"],
            is_active=bool(row["is_active"]),
            is_duplicate=bool(row["is_duplicate"]),
            created_at=row["created_at"],
        )


# ---------------------------------------------------------------------------
# ExtractionAttemptRepo
# ---------------------------------------------------------------------------

class ExtractionAttemptRepo:
    @staticmethod
    def insert(conn: sqlite3.Connection, attempt: ExtractionAttempt) -> None:
        conn.execute(
            """
            INSERT INTO extraction_attempts
                (attempt_id, run_id, chunk_id, prompt_version, model_name,
                 items_extracted, items_accepted, items_duplicate,
                 raw_response, error_message, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                attempt.attempt_id,
                attempt.run_id,
                attempt.chunk_id,
                attempt.prompt_version,
                attempt.model_name,
                attempt.items_extracted,
                attempt.items_accepted,
                attempt.items_duplicate,
                attempt.raw_response,
                attempt.error_message,
                _dt(attempt.created_at),
            ),
        )


# ---------------------------------------------------------------------------
# GroundingAssessmentRepo
# ---------------------------------------------------------------------------

class GroundingAssessmentRepo:
    @staticmethod
    def insert(conn: sqlite3.Connection, assessment: GroundingAssessment) -> None:
        conn.execute(
            """
            INSERT INTO grounding_assessments
                (assessment_id, run_id, knowledge_item_id, chunk_id, label,
                 score, prompt_version, model_name, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                assessment.assessment_id,
                assessment.run_id,
                assessment.knowledge_item_id,
                assessment.chunk_id,
                assessment.label.value,
                assessment.score,
                assessment.prompt_version,
                assessment.model_name,
                _dt(assessment.created_at),
            ),
        )
        # Insert evidence spans
        for span in assessment.evidence_spans:
            EvidenceSpanRepo.insert(conn, span)

    @staticmethod
    def get_by_item(conn: sqlite3.Connection, item_id: str) -> GroundingAssessment | None:
        row = conn.execute(
            "SELECT * FROM grounding_assessments WHERE knowledge_item_id = ? ORDER BY created_at DESC LIMIT 1",
            (item_id,),
        ).fetchone()
        if row is None:
            return None
        from anki_pipeline.enums import AssessmentLabel
        spans = EvidenceSpanRepo.get_by_item(conn, item_id)
        return GroundingAssessment(
            assessment_id=row["assessment_id"],
            run_id=row["run_id"],
            knowledge_item_id=row["knowledge_item_id"],
            chunk_id=row["chunk_id"],
            label=AssessmentLabel(row["label"]),
            score=row["score"],
            prompt_version=row["prompt_version"],
            model_name=row["model_name"],
            created_at=row["created_at"],
            evidence_spans=spans,
        )


# ---------------------------------------------------------------------------
# EvidenceSpanRepo
# ---------------------------------------------------------------------------

class EvidenceSpanRepo:
    @staticmethod
    def insert(conn: sqlite3.Connection, span: EvidenceSpan) -> None:
        conn.execute(
            """
            INSERT INTO evidence_spans
                (span_id, knowledge_item_id, chunk_id, char_start, char_end,
                 text, page_or_section)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                span.span_id,
                span.knowledge_item_id,
                span.chunk_id,
                span.char_start,
                span.char_end,
                span.text,
                span.page_or_section,
            ),
        )

    @staticmethod
    def get_by_item(conn: sqlite3.Connection, item_id: str) -> list[EvidenceSpan]:
        rows = conn.execute(
            "SELECT * FROM evidence_spans WHERE knowledge_item_id = ?", (item_id,)
        ).fetchall()
        return [
            EvidenceSpan(
                span_id=r["span_id"],
                knowledge_item_id=r["knowledge_item_id"],
                chunk_id=r["chunk_id"],
                char_start=r["char_start"],
                char_end=r["char_end"],
                text=r["text"],
                page_or_section=r["page_or_section"],
            )
            for r in rows
        ]


# ---------------------------------------------------------------------------
# RankingAssessmentRepo
# ---------------------------------------------------------------------------

class RankingAssessmentRepo:
    @staticmethod
    def insert(conn: sqlite3.Connection, ranking: RankingAssessment) -> None:
        conn.execute(
            """
            INSERT INTO ranking_assessments
                (ranking_id, run_id, knowledge_item_id, importance, forgettability,
                 testability, aggregate_score, estimated_card_cost, utility_density,
                 prompt_version, model_name, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ranking.ranking_id,
                ranking.run_id,
                ranking.knowledge_item_id,
                ranking.importance,
                ranking.forgettability,
                ranking.testability,
                ranking.aggregate_score,
                ranking.estimated_card_cost,
                ranking.utility_density,
                ranking.prompt_version,
                ranking.model_name,
                _dt(ranking.created_at),
            ),
        )

    @staticmethod
    def get_by_item(conn: sqlite3.Connection, item_id: str) -> RankingAssessment | None:
        row = conn.execute(
            "SELECT * FROM ranking_assessments WHERE knowledge_item_id = ? ORDER BY created_at DESC LIMIT 1",
            (item_id,),
        ).fetchone()
        if row is None:
            return None
        return RankingAssessment(
            ranking_id=row["ranking_id"],
            run_id=row["run_id"],
            knowledge_item_id=row["knowledge_item_id"],
            importance=row["importance"],
            forgettability=row["forgettability"],
            testability=row["testability"],
            aggregate_score=row["aggregate_score"],
            estimated_card_cost=row["estimated_card_cost"],
            utility_density=row["utility_density"],
            prompt_version=row["prompt_version"],
            model_name=row["model_name"],
            created_at=row["created_at"],
        )


# ---------------------------------------------------------------------------
# SelectionDecisionRepo
# ---------------------------------------------------------------------------

class SelectionDecisionRepo:
    @staticmethod
    def insert(conn: sqlite3.Connection, decision: SelectionDecision) -> None:
        conn.execute(
            """
            INSERT INTO selection_decisions
                (decision_id, run_id, knowledge_item_id, selected, reason,
                 budget_snapshot, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                decision.decision_id,
                decision.run_id,
                decision.knowledge_item_id,
                int(decision.selected),
                decision.reason.value,
                _json(decision.budget_snapshot),
                _dt(decision.created_at),
            ),
        )


# ---------------------------------------------------------------------------
# SynthesisAttemptRepo
# ---------------------------------------------------------------------------

class SynthesisAttemptRepo:
    @staticmethod
    def insert(conn: sqlite3.Connection, attempt: SynthesisAttempt) -> None:
        conn.execute(
            """
            INSERT INTO synthesis_attempts
                (attempt_id, run_id, knowledge_item_id, prompt_version, model_name,
                 notes_generated, notes_accepted, raw_response, error_message, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                attempt.attempt_id,
                attempt.run_id,
                attempt.knowledge_item_id,
                attempt.prompt_version,
                attempt.model_name,
                attempt.notes_generated,
                attempt.notes_accepted,
                attempt.raw_response,
                attempt.error_message,
                _dt(attempt.created_at),
            ),
        )


# ---------------------------------------------------------------------------
# NoteCandidateRepo
# ---------------------------------------------------------------------------

class NoteCandidateRepo:
    @staticmethod
    def insert(conn: sqlite3.Connection, candidate: NoteCandidate) -> None:
        conn.execute(
            """
            INSERT INTO note_candidates
                (candidate_id, run_id, knowledge_item_id, note_type, front, back,
                 text, back_extra, source_field, tags, note_identity_hash,
                 provenance_kind, synthesis_attempt_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                candidate.candidate_id,
                candidate.run_id,
                candidate.knowledge_item_id,
                candidate.note_type.value,
                candidate.front,
                candidate.back,
                candidate.text,
                candidate.back_extra,
                candidate.source_field,
                _json(candidate.tags),
                candidate.note_identity_hash,
                candidate.provenance_kind.value,
                candidate.synthesis_attempt_id,
                _dt(candidate.created_at),
            ),
        )

    @staticmethod
    def get_pending_for_review(conn: sqlite3.Connection, run_id: str | None = None) -> list[NoteCandidate]:
        """Get candidates that passed validation and have not been reviewed yet."""
        if run_id:
            rows = conn.execute(
                """
                SELECT nc.* FROM note_candidates nc
                JOIN validation_results vr ON vr.candidate_id = nc.candidate_id
                WHERE vr.passed = 1
                  AND nc.candidate_id NOT IN (SELECT candidate_id FROM review_actions)
                  AND nc.run_id = ?
                ORDER BY nc.created_at
                """,
                (run_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT nc.* FROM note_candidates nc
                JOIN validation_results vr ON vr.candidate_id = nc.candidate_id
                WHERE vr.passed = 1
                  AND nc.candidate_id NOT IN (SELECT candidate_id FROM review_actions)
                ORDER BY nc.created_at
                """,
            ).fetchall()
        return [NoteCandidateRepo._row_to_model(r) for r in rows]

    @staticmethod
    def _row_to_model(row: sqlite3.Row) -> NoteCandidate:
        from anki_pipeline.enums import NoteType, ProvenanceKind
        return NoteCandidate(
            candidate_id=row["candidate_id"],
            run_id=row["run_id"],
            knowledge_item_id=row["knowledge_item_id"],
            note_type=NoteType(row["note_type"]),
            front=row["front"],
            back=row["back"],
            text=row["text"],
            back_extra=row["back_extra"],
            source_field=row["source_field"] or "",
            tags=json.loads(row["tags"] or "[]"),
            note_identity_hash=row["note_identity_hash"] or "",
            provenance_kind=ProvenanceKind(row["provenance_kind"]),
            synthesis_attempt_id=row["synthesis_attempt_id"] or "",
            created_at=row["created_at"],
        )


# ---------------------------------------------------------------------------
# ValidationResultRepo
# ---------------------------------------------------------------------------

class ValidationResultRepo:
    @staticmethod
    def insert(conn: sqlite3.Connection, result: ValidationResult) -> None:
        conn.execute(
            """
            INSERT INTO validation_results
                (result_id, candidate_id, run_id, passed, failure_codes, warning_codes, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                result.result_id,
                result.candidate_id,
                result.run_id,
                int(result.passed),
                _json(result.failure_codes),
                _json(result.warning_codes),
                _dt(result.created_at),
            ),
        )


# ---------------------------------------------------------------------------
# ReviewActionRepo
# ---------------------------------------------------------------------------

class ReviewActionRepo:
    @staticmethod
    def insert(conn: sqlite3.Connection, action: ReviewAction) -> None:
        conn.execute(
            """
            INSERT INTO review_actions
                (action_id, run_id, candidate_id, decision, edit_type,
                 edited_fields, reject_reason_code, reviewer_notes, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                action.action_id,
                action.run_id,
                action.candidate_id,
                action.decision.value,
                action.edit_type.value if action.edit_type else None,
                _json(action.edited_fields),
                action.reject_reason_code,
                action.reviewer_notes,
                _dt(action.created_at),
            ),
        )


# ---------------------------------------------------------------------------
# ReviewedNoteRepo
# ---------------------------------------------------------------------------

class ReviewedNoteRepo:
    @staticmethod
    def insert(conn: sqlite3.Connection, note: ReviewedNote) -> None:
        conn.execute(
            """
            INSERT INTO reviewed_notes
                (reviewed_note_id, run_id, candidate_id, action_id, note_type,
                 front, back, text, back_extra, source_field, tags,
                 note_identity_hash, provenance_kind, ready_for_export, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                note.reviewed_note_id,
                note.run_id,
                note.candidate_id,
                note.action_id,
                note.note_type.value,
                note.front,
                note.back,
                note.text,
                note.back_extra,
                note.source_field,
                _json(note.tags),
                note.note_identity_hash,
                note.provenance_kind.value,
                int(note.ready_for_export),
                _dt(note.created_at),
            ),
        )

    @staticmethod
    def get_ready_for_export(
        conn: sqlite3.Connection,
        deck_target: str | None = None,
        export_method: str = "tsv",
    ) -> list[ReviewedNote]:
        """Get reviewed notes ready for export that haven't been exported by method."""
        if deck_target:
            rows = conn.execute(
                """
                SELECT rn.* FROM reviewed_notes rn
                JOIN note_candidates nc ON nc.candidate_id = rn.candidate_id
                JOIN knowledge_items ki ON ki.item_id = nc.knowledge_item_id
                WHERE rn.ready_for_export = 1
                  AND ki.deck_target = ?
                  AND rn.reviewed_note_id NOT IN (
                      SELECT reviewed_note_id FROM export_records
                      WHERE status = 'success' AND export_method = ?
                  )
                ORDER BY rn.created_at
                """,
                (deck_target, export_method),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT rn.* FROM reviewed_notes rn
                WHERE rn.ready_for_export = 1
                  AND rn.reviewed_note_id NOT IN (
                      SELECT reviewed_note_id FROM export_records
                      WHERE status = 'success' AND export_method = ?
                  )
                ORDER BY rn.created_at
                """,
                (export_method,),
            ).fetchall()
        return [ReviewedNoteRepo._row_to_model(r) for r in rows]

    @staticmethod
    def _row_to_model(row: sqlite3.Row) -> ReviewedNote:
        from anki_pipeline.enums import NoteType, ProvenanceKind
        return ReviewedNote(
            reviewed_note_id=row["reviewed_note_id"],
            run_id=row["run_id"],
            candidate_id=row["candidate_id"],
            action_id=row["action_id"],
            note_type=NoteType(row["note_type"]),
            front=row["front"],
            back=row["back"],
            text=row["text"],
            back_extra=row["back_extra"],
            source_field=row["source_field"] or "",
            tags=json.loads(row["tags"] or "[]"),
            note_identity_hash=row["note_identity_hash"] or "",
            provenance_kind=ProvenanceKind(row["provenance_kind"]),
            ready_for_export=bool(row["ready_for_export"]),
            created_at=row["created_at"],
        )


# ---------------------------------------------------------------------------
# ExportRecordRepo
# ---------------------------------------------------------------------------

class ExportRecordRepo:
    @staticmethod
    def insert(conn: sqlite3.Connection, record: ExportRecord) -> None:
        conn.execute(
            """
            INSERT INTO export_records
                (export_id, reviewed_note_id, run_id, deck_target, tsv_row,
                 export_method, status, output_file, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.export_id,
                record.reviewed_note_id,
                record.run_id,
                record.deck_target,
                record.tsv_row,
                record.export_method,
                record.status,
                record.output_file,
                _dt(record.created_at),
            ),
        )

    @staticmethod
    def exists_success(
        conn: sqlite3.Connection,
        reviewed_note_id: str,
        export_method: str = "tsv",
    ) -> bool:
        row = conn.execute(
            """
            SELECT 1 FROM export_records
            WHERE reviewed_note_id = ? AND export_method = ? AND status = 'success'
            """,
            (reviewed_note_id, export_method),
        ).fetchone()
        return row is not None
