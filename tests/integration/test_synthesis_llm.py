"""Integration tests for LLM synthesis (require ANTHROPIC_API_KEY)."""

import os
import pytest
from pathlib import Path

from anki_pipeline.enums import KnowledgeItemType, ProvenanceKind
from anki_pipeline.identity import generate_id
from anki_pipeline.llm.client import LLMClient
from anki_pipeline.models import KnowledgeItem
from anki_pipeline.prompt_registry import PromptRegistry
from anki_pipeline.retrieval_design.synthesis import synthesize_notes


@pytest.mark.llm
@pytest.mark.parametrize("item_type", [
    KnowledgeItemType.definition,
    KnowledgeItemType.formula,
    KnowledgeItemType.distinction,
])
def test_synthesis_produces_valid_note(item_type):
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        pytest.skip("ANTHROPIC_API_KEY not set")

    claims = {
        KnowledgeItemType.definition: "A derivative measures the instantaneous rate of change.",
        KnowledgeItemType.formula: "The power rule states d/dx[x^n] = n*x^(n-1).",
        KnowledgeItemType.distinction: "unique_ptr has exclusive ownership while shared_ptr allows shared ownership.",
    }

    item = KnowledgeItem(
        item_id=generate_id(),
        run_id=generate_id(),
        item_type=item_type,
        claim=claims[item_type],
        content_hash=generate_id(),
        deck_target="Test",
        subject_tag_root="test",
    )

    llm = LLMClient(api_key=api_key)
    prompts = PromptRegistry(
        Path(__file__).parent.parent.parent / "src" / "anki_pipeline" / "config" / "prompts"
    )

    candidates, attempt = synthesize_notes(item, [], llm, prompts, run_id=item.run_id)
    assert attempt.error_message is None
    assert len(candidates) == 1

    candidate = candidates[0]
    assert candidate.note_identity_hash
    assert candidate.note_type is not None
