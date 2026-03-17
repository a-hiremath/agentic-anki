"""Tests for synthesis-time note normalization."""

from __future__ import annotations

from pathlib import Path

from anki_pipeline.enums import KnowledgeItemType, NoteType
from anki_pipeline.identity import generate_id, note_identity_hash
from anki_pipeline.llm.schemas import SynthesizedBasicNote, SynthesizedClozeNote
from anki_pipeline.models import KnowledgeItem
from anki_pipeline.prompt_registry import PromptRegistry
from anki_pipeline.retrieval_design.synthesis import synthesize_notes
from tests.conftest import MockLLMClient


PROMPTS_DIR = Path(__file__).parent.parent.parent / "src" / "anki_pipeline" / "config" / "prompts"


def make_item(item_type: KnowledgeItemType) -> KnowledgeItem:
    return KnowledgeItem(
        item_id=generate_id(),
        run_id=generate_id(),
        item_type=item_type,
        claim="Synthetic test claim",
        content_hash=generate_id(),
        deck_target="Test",
        subject_tag_root="test",
    )


class TestSynthesizeNotesNormalization:
    def test_basic_note_fields_are_normalized_before_hashing(self):
        item = make_item(KnowledgeItemType.formula)
        llm = MockLLMClient({
            SynthesizedBasicNote: SynthesizedBasicNote(
                front="What is $x$?",
                back="Use $$x^2 + 1$$.",
                back_extra="Valid for $x > 0$.",
            )
        })
        prompts = PromptRegistry(PROMPTS_DIR)

        candidates, attempt = synthesize_notes(item, [], llm, prompts, run_id=item.run_id)

        assert attempt.error_message is None
        candidate = candidates[0]
        assert candidate.note_type == NoteType.stem_basic
        assert candidate.front == r"What is \(x\)?"
        assert candidate.back == r"Use \[x^2 + 1\]."
        assert candidate.back_extra == r"Valid for \(x > 0\)."
        assert candidate.note_identity_hash == note_identity_hash(
            NoteType.stem_basic,
            front=candidate.front,
            back=candidate.back,
            back_extra=candidate.back_extra,
        )

    def test_cloze_note_fields_are_normalized_before_hashing(self):
        item = make_item(KnowledgeItemType.procedure)
        llm = MockLLMClient({
            SynthesizedClozeNote: SynthesizedClozeNote(
                text="The derivative of $x^n$ is {{c1::$nx^{n-1}$}}.",
                back_extra="Use only when $n$ is constant.",
            )
        })
        prompts = PromptRegistry(PROMPTS_DIR)

        candidates, attempt = synthesize_notes(item, [], llm, prompts, run_id=item.run_id)

        assert attempt.error_message is None
        candidate = candidates[0]
        assert candidate.note_type == NoteType.stem_cloze
        assert candidate.text == r"The derivative of \(x^n\) is {{c1::\(nx^{n-1}\)}}."
        assert candidate.back_extra == r"Use only when \(n\) is constant."
        assert candidate.note_identity_hash == note_identity_hash(
            NoteType.stem_cloze,
            text=candidate.text,
            back_extra=candidate.back_extra,
        )
