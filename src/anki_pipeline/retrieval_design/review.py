"""Terminal review UI with rich display and $EDITOR edit flow (Spec Section 16)."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
from rich.text import Text

from anki_pipeline.config import ReviewConfig
from anki_pipeline.enums import EditType, NoteType, ProvenanceKind, ReviewDecision
from anki_pipeline.identity import generate_id, note_identity_hash
from anki_pipeline.models import NoteCandidate, ReviewAction, ReviewedNote
from anki_pipeline.normalize import normalize_cosmetic
from anki_pipeline.retrieval_design.validation import validate_note
from anki_pipeline.storage import (
    Database,
    NoteCandidateRepo,
    ReviewActionRepo,
    ReviewedNoteRepo,
    ValidationResultRepo,
)

logger = logging.getLogger(__name__)
console = Console()

_REJECT_REASONS = [
    "ambiguous", "incorrect", "duplicate", "too_complex",
    "poorly_worded", "out_of_scope", "trivial", "other",
]


def review_session(
    db: Database,
    run_id: str | None,
    config: ReviewConfig,
    deck: str | None = None,
) -> list[ReviewAction]:
    """Run an interactive terminal review session.

    Returns list of ReviewActions taken in this session.
    """
    with db.connect() as conn:
        candidates = NoteCandidateRepo.get_pending_for_review(conn, run_id=run_id)

    if not candidates:
        console.print("[yellow]No pending notes to review.[/yellow]")
        return []

    console.print(f"\n[bold green]Review session: {len(candidates)} notes pending[/bold green]\n")

    actions: list[ReviewAction] = []
    for i, candidate in enumerate(candidates):
        console.print(f"\n[dim]Note {i+1}/{len(candidates)}[/dim]")
        action = _review_single(candidate, db, config)
        actions.append(action)

        if action.decision == ReviewDecision.skip:
            continue  # candidate stays pending
        if action.decision == ReviewDecision.reject:
            _persist_reject(db, candidate, action)
        elif action.decision in (ReviewDecision.accept, ReviewDecision.edit):
            reviewed = _build_reviewed_note(candidate, action)
            _persist_accept(db, candidate, action, reviewed, config)

        # Check for quit
        if hasattr(action, '_quit') and action._quit:  # type: ignore[attr-defined]
            break

    return actions


def _review_single(
    candidate: NoteCandidate,
    db: Database,
    config: ReviewConfig,
) -> ReviewAction:
    """Display a single candidate and collect a review decision."""
    _display_candidate(candidate)

    while True:
        choice = Prompt.ask(
            "[bold]Action[/bold] [dim](a)ccept  (r)eject  (e)dit  (s)kip  (q)uit[/dim]",
            choices=["a", "r", "e", "s", "q", "accept", "reject", "edit", "skip", "quit"],
            default="a",
        ).lower()[0]  # take first char

        if choice == "a":
            return ReviewAction(
                action_id=generate_id(),
                run_id=candidate.run_id,
                candidate_id=candidate.candidate_id,
                decision=ReviewDecision.accept,
            )

        elif choice == "r":
            reason = Prompt.ask(
                "Reject reason",
                choices=_REJECT_REASONS,
                default="other",
            )
            return ReviewAction(
                action_id=generate_id(),
                run_id=candidate.run_id,
                candidate_id=candidate.candidate_id,
                decision=ReviewDecision.reject,
                reject_reason_code=reason,
            )

        elif choice == "e":
            return _edit_candidate(candidate)

        elif choice == "s":
            return ReviewAction(
                action_id=generate_id(),
                run_id=candidate.run_id,
                candidate_id=candidate.candidate_id,
                decision=ReviewDecision.skip,
            )

        elif choice == "q":
            action = ReviewAction(
                action_id=generate_id(),
                run_id=candidate.run_id,
                candidate_id=candidate.candidate_id,
                decision=ReviewDecision.skip,
            )
            action._quit = True  # type: ignore[attr-defined]
            return action


def _display_candidate(candidate: NoteCandidate) -> None:
    """Render a candidate note to the terminal."""
    if candidate.note_type == NoteType.stem_basic:
        content = (
            f"[bold cyan]FRONT:[/bold cyan]\n{candidate.front}\n\n"
            f"[bold cyan]BACK:[/bold cyan]\n{candidate.back}"
        )
        if candidate.back_extra:
            content += f"\n\n[dim]EXTRA: {candidate.back_extra}[/dim]"
    else:
        content = f"[bold cyan]TEXT:[/bold cyan]\n{candidate.text}"
        if candidate.back_extra:
            content += f"\n\n[dim]EXTRA: {candidate.back_extra}[/dim]"

    meta = (
        f"[dim]Type: {candidate.note_type.value} | "
        f"Provenance: {candidate.provenance_kind.value} | "
        f"Tags: {', '.join(candidate.tags) or 'none'}[/dim]"
    )
    if candidate.source_field:
        meta += f"\n[dim]Source: {candidate.source_field}[/dim]"

    console.print(Panel(content, title=f"[bold]{candidate.note_type.value}[/bold]"))
    console.print(meta)


def _edit_candidate(candidate: NoteCandidate) -> ReviewAction:
    """Open note fields in $EDITOR for editing."""
    # Serialize editable fields to JSON
    if candidate.note_type == NoteType.stem_basic:
        fields = {
            "front": candidate.front or "",
            "back": candidate.back or "",
            "back_extra": candidate.back_extra or "",
            "tags": candidate.tags,
        }
    else:
        fields = {
            "text": candidate.text or "",
            "back_extra": candidate.back_extra or "",
            "tags": candidate.tags,
        }

    original_json = json.dumps(fields, indent=2)

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    ) as tf:
        tf.write(original_json)
        tmp_path = tf.name

    try:
        editor = os.environ.get("EDITOR") or ("notepad" if sys.platform == "win32" else "vim")
        subprocess.run([editor, tmp_path], check=True)
        edited_json = Path(tmp_path).read_text(encoding="utf-8")
        edited_fields = json.loads(edited_json)
    except Exception as exc:
        console.print(f"[red]Editor error: {exc}[/red]")
        return ReviewAction(
            action_id=generate_id(),
            run_id=candidate.run_id,
            candidate_id=candidate.candidate_id,
            decision=ReviewDecision.skip,
        )
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    # Classify edit type
    orig_norm = normalize_cosmetic(original_json)
    edit_norm = normalize_cosmetic(edited_json)
    edit_type = EditType.cosmetic if orig_norm == edit_norm else EditType.semantic

    return ReviewAction(
        action_id=generate_id(),
        run_id=candidate.run_id,
        candidate_id=candidate.candidate_id,
        decision=ReviewDecision.edit,
        edit_type=edit_type,
        edited_fields={k: str(v) for k, v in edited_fields.items() if isinstance(v, (str, list))},
    )


def _build_reviewed_note(
    candidate: NoteCandidate, action: ReviewAction
) -> ReviewedNote:
    """Build a ReviewedNote from a candidate + action (Spec Section 17)."""
    # Start with candidate fields
    front = candidate.front
    back = candidate.back
    text = candidate.text
    back_extra = candidate.back_extra
    tags = list(candidate.tags)
    provenance = candidate.provenance_kind

    # Apply edits if any
    if action.decision == ReviewDecision.edit and action.edited_fields:
        ef = action.edited_fields
        if "front" in ef:
            front = ef["front"]
        if "back" in ef:
            back = ef["back"]
        if "text" in ef:
            text = ef["text"]
        if "back_extra" in ef:
            back_extra = ef["back_extra"] or None
        if "tags" in ef:
            try:
                tags = json.loads(ef["tags"]) if isinstance(ef["tags"], str) else ef["tags"]
            except (json.JSONDecodeError, TypeError):
                pass

        # Update provenance for semantic edits
        if action.edit_type == EditType.semantic:
            if provenance == ProvenanceKind.source_extracted:
                provenance = ProvenanceKind.human_edited
            elif provenance != ProvenanceKind.user_attested:
                provenance = ProvenanceKind.mixed

    # Recompute identity hash with final fields
    if candidate.note_type == NoteType.stem_basic:
        identity = note_identity_hash(
            NoteType.stem_basic, front=front, back=back, back_extra=back_extra
        )
    else:
        identity = note_identity_hash(
            NoteType.stem_cloze, text=text, back_extra=back_extra
        )

    return ReviewedNote(
        reviewed_note_id=generate_id(),
        run_id=candidate.run_id,
        candidate_id=candidate.candidate_id,
        action_id=action.action_id,
        note_type=candidate.note_type,
        front=front,
        back=back,
        text=text,
        back_extra=back_extra,
        source_field=candidate.source_field,
        tags=tags,
        note_identity_hash=identity,
        provenance_kind=provenance,
        ready_for_export=True,
    )


def _persist_reject(
    db: Database, candidate: NoteCandidate, action: ReviewAction
) -> None:
    with db.connect() as conn:
        ReviewActionRepo.insert(conn, action)


def _persist_accept(
    db: Database,
    candidate: NoteCandidate,
    action: ReviewAction,
    reviewed: ReviewedNote,
    config: ReviewConfig,
) -> None:
    """Persist action + reviewed note atomically, re-running validation if edited."""
    from anki_pipeline.config import ValidationConfig
    validation_config = ValidationConfig()

    if action.decision == ReviewDecision.edit:
        # Re-run deterministic validation on edited note
        temp_candidate = NoteCandidate(
            candidate_id=candidate.candidate_id,
            run_id=candidate.run_id,
            knowledge_item_id=candidate.knowledge_item_id,
            note_type=reviewed.note_type,
            front=reviewed.front,
            back=reviewed.back,
            text=reviewed.text,
            back_extra=reviewed.back_extra,
            source_field=reviewed.source_field,
            tags=reviewed.tags,
            note_identity_hash=reviewed.note_identity_hash,
            provenance_kind=reviewed.provenance_kind,
        )
        result = validate_note(temp_candidate, validation_config)
        if not result.passed:
            console.print(
                f"[red]Edited note failed validation: {result.failure_codes}[/red]"
            )
            reviewed.ready_for_export = False

    with db.connect() as conn:
        ReviewActionRepo.insert(conn, action)
        ReviewedNoteRepo.insert(conn, reviewed)
        if action.decision == ReviewDecision.edit:
            result = validate_note(
                NoteCandidate(
                    candidate_id=candidate.candidate_id,
                    run_id=candidate.run_id,
                    knowledge_item_id=candidate.knowledge_item_id,
                    note_type=reviewed.note_type,
                    front=reviewed.front,
                    back=reviewed.back,
                    text=reviewed.text,
                    back_extra=reviewed.back_extra,
                    source_field=reviewed.source_field,
                    tags=reviewed.tags,
                    note_identity_hash=reviewed.note_identity_hash,
                    provenance_kind=reviewed.provenance_kind,
                ),
                validation_config,
            )
            ValidationResultRepo.insert(conn, result)
