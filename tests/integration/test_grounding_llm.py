"""Integration tests for LLM grounding (require ANTHROPIC_API_KEY)."""

import os
import pytest
from pathlib import Path

from anki_pipeline.distillation.grounding import assess_grounding
from anki_pipeline.enums import AssessmentLabel, EntryMode, KnowledgeItemType, ProvenanceKind
from anki_pipeline.identity import generate_id
from anki_pipeline.llm.client import LLMClient
from anki_pipeline.models import Chunk, KnowledgeItem, SourceRecord
from anki_pipeline.prompt_registry import PromptRegistry


@pytest.mark.llm
def test_direct_grounding():
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        pytest.skip("ANTHROPIC_API_KEY not set")

    chunk_text = "The power rule: $(x^n)' = nx^{n-1}$ for all real $n$."
    source = SourceRecord(
        source_id=generate_id(), run_id=generate_id(),
        entry_mode=EntryMode.document, canonical_text=chunk_text,
        source_fingerprint=generate_id(), char_count=len(chunk_text),
    )
    chunk = Chunk(
        chunk_id=generate_id(), source_id=source.source_id, run_id=source.run_id,
        ordinal=0, char_start=0, char_end=len(chunk_text), text=chunk_text,
    )
    item = KnowledgeItem(
        item_id=generate_id(), run_id=source.run_id,
        item_type=KnowledgeItemType.formula,
        claim="The derivative of x^n is n*x^(n-1).",
        content_hash=generate_id(), deck_target="Math",
    )

    llm = LLMClient(api_key=api_key)
    prompts = PromptRegistry(
        Path(__file__).parent.parent.parent / "src" / "anki_pipeline" / "config" / "prompts"
    )

    assessment = assess_grounding(item, chunk, source, llm, prompts, run_id=source.run_id)
    assert assessment.label in (AssessmentLabel.direct, AssessmentLabel.inferential)
    assert assessment.score is not None
    assert 0.0 <= assessment.score <= 1.0


@pytest.mark.llm
def test_unsupported_grounding():
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        pytest.skip("ANTHROPIC_API_KEY not set")

    chunk_text = "The sky is blue due to Rayleigh scattering."
    source = SourceRecord(
        source_id=generate_id(), run_id=generate_id(),
        entry_mode=EntryMode.document, canonical_text=chunk_text,
        source_fingerprint=generate_id(), char_count=len(chunk_text),
    )
    chunk = Chunk(
        chunk_id=generate_id(), source_id=source.source_id, run_id=source.run_id,
        ordinal=0, char_start=0, char_end=len(chunk_text), text=chunk_text,
    )
    item = KnowledgeItem(
        item_id=generate_id(), run_id=source.run_id,
        item_type=KnowledgeItemType.formula,
        claim="The power rule is d/dx[x^n] = nx^(n-1).",
        content_hash=generate_id(), deck_target="Math",
    )

    llm = LLMClient(api_key=api_key)
    prompts = PromptRegistry(
        Path(__file__).parent.parent.parent / "src" / "anki_pipeline" / "config" / "prompts"
    )

    assessment = assess_grounding(item, chunk, source, llm, prompts, run_id=source.run_id)
    assert assessment.label == AssessmentLabel.unsupported
