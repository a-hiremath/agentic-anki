"""TSV export for Anki import (Spec Section 18)."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from pathlib import Path

from anki_pipeline.config import ExportConfig
from anki_pipeline.enums import NoteType
from anki_pipeline.identity import generate_id
from anki_pipeline.models import ExportRecord, ReviewedNote
from anki_pipeline.storage import Database, ExportRecordRepo, ReviewedNoteRepo

logger = logging.getLogger(__name__)

# TSV column headers per note type
_BASIC_HEADERS = ["#notetype:STEMBasic", "#deck", "ExternalID", "Front", "Back", "BackExtra", "Source", "Tags"]
_CLOZE_HEADERS = ["#notetype:STEMCloze", "#deck", "ExternalID", "Text", "BackExtra", "Source", "Tags"]


@dataclass(slots=True)
class ExportResult:
    records: list[ExportRecord]
    n_added: int = 0
    n_failed: int = 0


def _escape_field(value: str | None) -> str:
    """Escape a field for TSV output.

    - tabs → 4 spaces
    - newlines → <br>
    - null → empty string
    """
    if value is None:
        return ""
    value = value.replace("\t", "    ")
    value = value.replace("\r\n", "<br>").replace("\n", "<br>").replace("\r", "<br>")
    return value


def _note_to_tsv_row(note: ReviewedNote, deck: str) -> str:
    """Convert a ReviewedNote to a TSV row string."""
    tags_str = " ".join(note.tags)

    if note.note_type == NoteType.stem_basic:
        fields = [
            "STEMBasic",
            _escape_field(deck),
            _escape_field(note.reviewed_note_id),
            _escape_field(note.front),
            _escape_field(note.back),
            _escape_field(note.back_extra),
            _escape_field(note.source_field),
            _escape_field(tags_str),
        ]
    elif note.note_type == NoteType.stem_cloze:
        fields = [
            "STEMCloze",
            _escape_field(deck),
            _escape_field(note.reviewed_note_id),
            _escape_field(note.text),
            _escape_field(note.back_extra),
            _escape_field(note.source_field),
            _escape_field(tags_str),
        ]
    else:
        raise ValueError(f"Unknown note type: {note.note_type!r}")

    return "\t".join(fields)


def export_to_tsv(
    reviewed_notes: list[ReviewedNote],
    output_dir: Path,
    deck: str,
    run_id: str,
    db: Database,
) -> ExportResult:
    """Export reviewed notes to a TSV file for Anki import.

    Idempotent: notes with an existing successful export record are skipped.

    Returns the list of ExportRecord objects created in this call.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_deck = deck.replace("::", "_").replace(" ", "_")
    output_path = output_dir / f"{safe_deck}.tsv"

    records: list[ExportRecord] = []
    basic_rows: list[str] = []
    cloze_rows: list[str] = []

    with db.connect() as conn:
        for note in reviewed_notes:
            if not note.ready_for_export:
                continue
            if ExportRecordRepo.exists_success(conn, note.reviewed_note_id, export_method="tsv"):
                logger.debug("Skipping already-exported note: %s", note.reviewed_note_id)
                continue

            tsv_row = _note_to_tsv_row(note, deck)

            if note.note_type == NoteType.stem_basic:
                basic_rows.append(tsv_row)
            else:
                cloze_rows.append(tsv_row)

            record = ExportRecord(
                export_id=generate_id(),
                reviewed_note_id=note.reviewed_note_id,
                run_id=run_id,
                deck_target=deck,
                tsv_row=tsv_row,
                export_method="tsv",
                status="success",
                output_file=str(output_path),
            )
            records.append(record)
            ExportRecordRepo.insert(conn, record)

    if not records:
        logger.info("No new notes to export for deck %r", deck)
        return ExportResult(records=[])

    # Write TSV file (append if exists, with headers only if new file)
    file_exists = output_path.exists()
    with output_path.open("a", encoding="utf-8", newline="") as fh:
        if not file_exists:
            # Write header comment
            fh.write(f"# Anki import for deck: {deck}\n")

        for row in basic_rows:
            fh.write(row + "\n")
        for row in cloze_rows:
            fh.write(row + "\n")

    logger.info(
        "Exported %d notes to %s (%d basic, %d cloze)",
        len(records), output_path, len(basic_rows), len(cloze_rows)
    )
    return ExportResult(records=records, n_added=len(records), n_failed=0)


def export_to_anki_connect(
    reviewed_notes: list[ReviewedNote],
    output_dir: Path,
    deck: str,
    run_id: str,
    db: Database,
    client: object,
) -> ExportResult:
    """Export reviewed notes directly into Anki via AnkiConnect."""
    from anki_pipeline.retrieval_design.anki_connect import AnkiConnectClient, AnkiConnectError

    if not isinstance(client, AnkiConnectClient):
        # Tests use a mock with the same public surface; keep the runtime contract loose.
        required = ("ensure_deck", "ensure_note_types", "add_note")
        missing = [name for name in required if not hasattr(client, name)]
        if missing:
            raise TypeError(f"client is missing required methods: {missing}")

    output_dir.mkdir(parents=True, exist_ok=True)
    safe_deck = deck.replace("::", "_").replace(" ", "_")
    audit_path = output_dir / f"{safe_deck}.tsv"

    records: list[ExportRecord] = []
    audit_rows: list[str] = []
    n_added = 0
    n_failed = 0

    client.ensure_deck(deck)
    client.ensure_note_types()

    with db.connect() as conn:
        for note in reviewed_notes:
            if not note.ready_for_export:
                continue
            if ExportRecordRepo.exists_success(conn, note.reviewed_note_id, export_method="direct"):
                logger.debug("Skipping already-direct-exported note: %s", note.reviewed_note_id)
                continue

            tsv_row = _note_to_tsv_row(note, deck)
            status = "success"

            try:
                client.add_note(deck, note)
                audit_rows.append(tsv_row)
                n_added += 1
            except AnkiConnectError as exc:
                logger.error("AnkiConnect failed for note %s: %s", note.reviewed_note_id, exc)
                status = "failed"
                n_failed += 1

            record = ExportRecord(
                export_id=generate_id(),
                reviewed_note_id=note.reviewed_note_id,
                run_id=run_id,
                deck_target=deck,
                tsv_row=tsv_row,
                export_method="direct",
                status=status,
                output_file=str(audit_path),
            )
            records.append(record)
            ExportRecordRepo.insert(conn, record)

    if audit_rows:
        file_exists = audit_path.exists()
        with audit_path.open("a", encoding="utf-8", newline="") as fh:
            if not file_exists:
                fh.write(f"# AnkiConnect audit for deck: {deck}\n")
            for row in audit_rows:
                fh.write(row + "\n")

    logger.info(
        "AnkiConnect export for %r: %d added, %d failed",
        deck, n_added, n_failed,
    )
    return ExportResult(records=records, n_added=n_added, n_failed=n_failed)


def export_deck(
    db: Database,
    deck: str,
    run_id: str,
    output_dir: Path,
    config: ExportConfig | None = None,
) -> ExportResult:
    """Export all ready-for-export reviewed notes for a deck."""
    config = config or ExportConfig()
    with db.connect() as conn:
        notes = ReviewedNoteRepo.get_ready_for_export(
            conn,
            deck_target=deck,
            export_method=config.method,
        )

    if config.method == "direct":
        from anki_pipeline.retrieval_design.anki_connect import AnkiConnectClient

        client = AnkiConnectClient(
            url=config.anki_connect_url,
            timeout=config.anki_connect_timeout,
        )
        return export_to_anki_connect(notes, output_dir, deck, run_id, db, client)

    return export_to_tsv(notes, output_dir, deck, run_id, db)
