"""Tests for export paths."""

from pathlib import Path
from unittest.mock import MagicMock

from anki_pipeline.enums import EntryMode, NoteType, ProvenanceKind
from anki_pipeline.identity import generate_id
from anki_pipeline.models import PipelineRun, ReviewedNote
from anki_pipeline.retrieval_design.anki_connect import AnkiConnectError
from anki_pipeline.retrieval_design.export import (
    _note_to_tsv_row,
    export_to_anki_connect,
    export_to_tsv,
)
from anki_pipeline.storage import Database, ExportRecordRepo, RunRepo


def make_basic_note(run_id: str = "run1", **kwargs) -> ReviewedNote:
    defaults = dict(
        reviewed_note_id=generate_id(),
        run_id=run_id,
        candidate_id=generate_id(),
        action_id=generate_id(),
        note_type=NoteType.stem_basic,
        front="What is a derivative?",
        back="The instantaneous rate of change of a function.",
        back_extra="Think: slope of tangent line.",
        source_field="Lecture 3, p.5",
        tags=["math.calc1c", "type::definition"],
        note_identity_hash=generate_id(),
        provenance_kind=ProvenanceKind.source_extracted,
    )
    defaults.update(kwargs)
    return ReviewedNote(**defaults)


def make_cloze_note(run_id: str = "run1", **kwargs) -> ReviewedNote:
    defaults = dict(
        reviewed_note_id=generate_id(),
        run_id=run_id,
        candidate_id=generate_id(),
        action_id=generate_id(),
        note_type=NoteType.stem_cloze,
        text="The derivative of $x^n$ is {{c1::$nx^{n-1}$}} by the power rule.",
        back_extra="Valid for all real n.",
        source_field="Lecture 3, p.7",
        tags=["math.calc1c", "type::formula"],
        note_identity_hash=generate_id(),
        provenance_kind=ProvenanceKind.source_extracted,
    )
    defaults.update(kwargs)
    return ReviewedNote(**defaults)


def setup_db_with_run(tmp_path: Path) -> tuple[Database, str]:
    db = Database(tmp_path / "test.db")
    run_id = generate_id()
    run = PipelineRun(
        run_id=run_id,
        entry_mode=EntryMode.document,
        deck_target="Math::Calc",
    )
    with db.connect() as conn:
        RunRepo.insert(conn, run)
    return db, run_id


class TestNoteToTsvRow:
    def test_basic_row_has_correct_columns(self):
        note = make_basic_note()
        row = _note_to_tsv_row(note, "Math::Calc")
        cols = row.split("\t")
        assert cols[0] == "STEMBasic"
        assert cols[1] == "Math::Calc"
        assert cols[2] == note.reviewed_note_id  # ExternalID
        assert cols[3] == note.front
        assert cols[4] == note.back
        assert cols[5] == note.back_extra
        assert cols[6] == note.source_field
        assert cols[7] == "math.calc1c type::definition"

    def test_cloze_row_has_correct_columns(self):
        note = make_cloze_note()
        row = _note_to_tsv_row(note, "Math::Calc")
        cols = row.split("\t")
        assert cols[0] == "STEMCloze"
        assert cols[2] == note.reviewed_note_id

    def test_tabs_in_field_escaped(self):
        note = make_basic_note(front="Q?\tWith tab")
        row = _note_to_tsv_row(note, "Math")
        # Tabs in content should become 4 spaces
        assert "\t" not in row.split("\t")[3]  # front field
        assert "    With tab" in row.split("\t")[3]

    def test_newlines_in_field_become_br(self):
        note = make_basic_note(back="Line1\nLine2\nLine3")
        row = _note_to_tsv_row(note, "Math")
        back_field = row.split("\t")[4]
        assert "<br>" in back_field
        assert "\n" not in back_field


class TestExportToTsv:
    def test_basic_export_creates_file(self, tmp_path: Path):
        db, run_id = setup_db_with_run(tmp_path)
        notes = [make_basic_note(run_id)]
        result = export_to_tsv(notes, tmp_path / "output", "Math::Calc", run_id, db)
        assert len(result.records) == 1
        output_file = Path(result.records[0].output_file)
        assert output_file.exists()

    def test_idempotent_export(self, tmp_path: Path):
        db, run_id = setup_db_with_run(tmp_path)
        note = make_basic_note(run_id)
        output_dir = tmp_path / "output"
        result1 = export_to_tsv([note], output_dir, "Math", run_id, db)
        result2 = export_to_tsv([note], output_dir, "Math", run_id, db)
        assert len(result1.records) == 1
        assert len(result2.records) == 0  # already exported

    def test_empty_list_returns_empty(self, tmp_path: Path):
        db, run_id = setup_db_with_run(tmp_path)
        result = export_to_tsv([], tmp_path / "output", "Math", run_id, db)
        assert result.records == []

    def test_mixed_types_exported(self, tmp_path: Path):
        db, run_id = setup_db_with_run(tmp_path)
        notes = [make_basic_note(run_id), make_cloze_note(run_id)]
        result = export_to_tsv(notes, tmp_path / "output", "Math", run_id, db)
        assert len(result.records) == 2

    def test_not_ready_for_export_skipped(self, tmp_path: Path):
        db, run_id = setup_db_with_run(tmp_path)
        note = make_basic_note(run_id, ready_for_export=False)
        result = export_to_tsv([note], tmp_path / "output", "Math", run_id, db)
        assert len(result.records) == 0

    def test_direct_success_does_not_block_tsv_export(self, tmp_path: Path):
        db, run_id = setup_db_with_run(tmp_path)
        note = make_basic_note(run_id)
        client = MagicMock()
        export_to_anki_connect([note], tmp_path / "out", "Math", run_id, db, client)

        result = export_to_tsv([note], tmp_path / "output", "Math", run_id, db)
        assert len(result.records) == 1


class TestExportToAnkiConnect:
    def _make_mock_client(self) -> MagicMock:
        client = MagicMock()
        client.ensure_deck.return_value = None
        client.ensure_note_types.return_value = None
        client.add_note.return_value = 99999
        return client

    def test_new_note_is_added(self, tmp_path: Path):
        db, run_id = setup_db_with_run(tmp_path)
        note = make_basic_note(run_id)
        client = self._make_mock_client()

        result = export_to_anki_connect([note], tmp_path / "out", "Math", run_id, db, client)

        assert result.n_added == 1
        assert result.n_failed == 0
        client.add_note.assert_called_once_with("Math", note)

    def test_idempotent_skips_already_direct_exported(self, tmp_path: Path):
        db, run_id = setup_db_with_run(tmp_path)
        note = make_basic_note(run_id)
        client = self._make_mock_client()

        first = export_to_anki_connect([note], tmp_path / "out", "Math", run_id, db, client)
        second = export_to_anki_connect([note], tmp_path / "out", "Math", run_id, db, client)

        assert len(first.records) == 1
        assert len(second.records) == 0
        client.add_note.assert_called_once()

    def test_tsv_success_does_not_block_direct_export(self, tmp_path: Path):
        db, run_id = setup_db_with_run(tmp_path)
        note = make_basic_note(run_id)
        export_to_tsv([note], tmp_path / "output", "Math", run_id, db)
        client = self._make_mock_client()

        result = export_to_anki_connect([note], tmp_path / "out", "Math", run_id, db, client)

        assert len(result.records) == 1
        client.add_note.assert_called_once()

    def test_ankiconnect_error_marks_record_failed(self, tmp_path: Path):
        db, run_id = setup_db_with_run(tmp_path)
        note = make_basic_note(run_id)
        client = self._make_mock_client()
        client.add_note.side_effect = AnkiConnectError("timeout")

        result = export_to_anki_connect([note], tmp_path / "out", "Math", run_id, db, client)

        assert result.records[0].status == "failed"
        assert result.n_added == 0
        assert result.n_failed == 1
        with db.connect() as conn:
            assert not ExportRecordRepo.exists_success(
                conn, note.reviewed_note_id, export_method="direct"
            )

    def test_audit_tsv_written_for_successful_notes(self, tmp_path: Path):
        db, run_id = setup_db_with_run(tmp_path)
        note = make_basic_note(run_id)
        client = self._make_mock_client()

        result = export_to_anki_connect([note], tmp_path / "out", "Math::Calc", run_id, db, client)

        audit_file = Path(result.records[0].output_file)
        assert audit_file.exists()
        contents = audit_file.read_text(encoding="utf-8")
        assert note.reviewed_note_id in contents
