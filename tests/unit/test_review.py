"""Tests for review-time note normalization."""

from __future__ import annotations

from rich.panel import Panel

from anki_pipeline.enums import EditType, NoteType, ProvenanceKind, ReviewDecision
from anki_pipeline.identity import generate_id, note_identity_hash
from anki_pipeline.models import NoteCandidate, ReviewAction
from anki_pipeline.retrieval_design import review as review_module
from anki_pipeline.retrieval_design.review import _build_reviewed_note, _display_candidate


def make_basic_candidate(**kwargs) -> NoteCandidate:
    defaults = dict(
        candidate_id=generate_id(),
        run_id=generate_id(),
        knowledge_item_id=generate_id(),
        note_type=NoteType.stem_basic,
        front="What is $x$?",
        back="It equals $$x^2$$.",
        provenance_kind=ProvenanceKind.source_extracted,
    )
    defaults.update(kwargs)
    return NoteCandidate(**defaults)


def make_cloze_candidate(**kwargs) -> NoteCandidate:
    defaults = dict(
        candidate_id=generate_id(),
        run_id=generate_id(),
        knowledge_item_id=generate_id(),
        note_type=NoteType.stem_cloze,
        text="The derivative of $x^n$ is {{c1::$nx^{n-1}$}}.",
        provenance_kind=ProvenanceKind.source_extracted,
    )
    defaults.update(kwargs)
    return NoteCandidate(**defaults)


class TestBuildReviewedNoteNormalization:
    def test_accept_path_normalizes_existing_raw_math(self):
        candidate = make_basic_candidate()
        action = ReviewAction(
            action_id=generate_id(),
            run_id=candidate.run_id,
            candidate_id=candidate.candidate_id,
            decision=ReviewDecision.accept,
        )

        reviewed = _build_reviewed_note(candidate, action)

        assert reviewed.front == r"What is \(x\)?"
        assert reviewed.back == r"It equals \[x^2\]."
        assert reviewed.note_identity_hash == note_identity_hash(
            NoteType.stem_basic,
            front=reviewed.front,
            back=reviewed.back,
            back_extra=reviewed.back_extra,
        )

    def test_edit_path_normalizes_edited_fields(self):
        candidate = make_cloze_candidate(text="Original {{c1::text}}.")
        action = ReviewAction(
            action_id=generate_id(),
            run_id=candidate.run_id,
            candidate_id=candidate.candidate_id,
            decision=ReviewDecision.edit,
            edit_type=EditType.semantic,
            edited_fields={
                "text": "The derivative of $x^n$ is {{c1::$nx^{n-1}$}}.",
                "back_extra": "Valid for $n > 0$.",
            },
        )

        reviewed = _build_reviewed_note(candidate, action)

        assert reviewed.text == r"The derivative of \(x^n\) is {{c1::\(nx^{n-1}\)}}."
        assert reviewed.back_extra == r"Valid for \(n > 0\)."
        assert reviewed.provenance_kind == ProvenanceKind.human_edited
        assert reviewed.note_identity_hash == note_identity_hash(
            NoteType.stem_cloze,
            text=reviewed.text,
            back_extra=reviewed.back_extra,
        )


class TestDisplayCandidate:
    def test_display_candidate_renders_math_for_terminal(self, monkeypatch):
        candidate = make_basic_candidate(
            front=r"What is \(\alpha + \beta\)?",
            back=r"It equals \[\frac{1}{2}\].",
        )
        renderables: list[object] = []

        monkeypatch.setattr(review_module.console, "print", lambda renderable, *args, **kwargs: renderables.append(renderable))

        _display_candidate(candidate)

        panel = renderables[0]
        assert isinstance(panel, Panel)
        assert panel.renderable.plain == "FRONT:\nWhat is α+ β?\n\nBACK:\nIt equals 1/2."
