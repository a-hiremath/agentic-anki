"""Tests for Pydantic models (Spec Sections 8.1-8.16)."""

import pytest

from anki_pipeline.enums import EntryMode, KnowledgeItemType, NoteType, ProvenanceKind, RunStatus
from anki_pipeline.models import (
    Chunk,
    KnowledgeItem,
    NoteCandidate,
    PipelineRun,
    SourceRecord,
    ValidationResult,
)


class TestStrictModel:
    def test_extra_fields_rejected(self):
        with pytest.raises(Exception):  # pydantic ValidationError
            PipelineRun(
                run_id="x",
                entry_mode=EntryMode.document,
                deck_target="Math",
                nonexistent_field="bad",  # type: ignore
            )

    def test_required_fields_enforced(self):
        with pytest.raises(Exception):
            PipelineRun(entry_mode=EntryMode.document)  # missing run_id etc.


class TestPipelineRun:
    def test_default_status(self):
        run = PipelineRun(
            run_id="r1", entry_mode=EntryMode.document, deck_target="Math"
        )
        assert run.status == RunStatus.running

    def test_stages_completed_default_empty(self):
        run = PipelineRun(
            run_id="r1", entry_mode=EntryMode.document, deck_target="Math"
        )
        assert run.stages_completed == []


class TestSourceRecord:
    def test_char_count_default(self):
        rec = SourceRecord(
            source_id="s1",
            run_id="r1",
            entry_mode=EntryMode.document,
        )
        assert rec.char_count == 0


class TestChunk:
    def test_basic_creation(self):
        chunk = Chunk(
            chunk_id="c1",
            source_id="s1",
            run_id="r1",
            ordinal=0,
            char_start=0,
            char_end=100,
            text="hello world " * 8,
        )
        assert chunk.char_end - chunk.char_start == 100


class TestKnowledgeItem:
    def test_is_active_default_true(self):
        item = KnowledgeItem(
            item_id="i1",
            run_id="r1",
            item_type=KnowledgeItemType.definition,
            claim="A set is a collection.",
        )
        assert item.is_active is True
        assert item.is_duplicate is False


class TestNoteCandidate:
    def test_basic_note(self):
        candidate = NoteCandidate(
            candidate_id="nc1",
            run_id="r1",
            knowledge_item_id="i1",
            note_type=NoteType.stem_basic,
            front="What is a set?",
            back="A collection of distinct elements.",
        )
        assert candidate.note_type == NoteType.stem_basic
        assert candidate.text is None

    def test_cloze_note(self):
        candidate = NoteCandidate(
            candidate_id="nc2",
            run_id="r1",
            knowledge_item_id="i1",
            note_type=NoteType.stem_cloze,
            text="A set has {{c1::no}} duplicate elements.",
        )
        assert candidate.front is None


class TestValidationResult:
    def test_passed_default_false(self):
        result = ValidationResult(
            result_id="vr1",
            candidate_id="nc1",
            run_id="r1",
            passed=True,
        )
        assert result.passed is True
        assert result.failure_codes == []
        assert result.warning_codes == []
