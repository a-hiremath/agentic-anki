"""Unit tests for batch grounding."""

from __future__ import annotations

from pathlib import Path

from anki_pipeline.distillation.grounding import assess_grounding, assess_grounding_batch
from anki_pipeline.enums import AssessmentLabel, EntryMode, KnowledgeItemType, ProvenanceKind
from anki_pipeline.identity import generate_id
from anki_pipeline.llm.schemas import (
    BatchGroundingItem,
    BatchGroundingResponse,
    GroundingResponse,
)
from anki_pipeline.models import Chunk, KnowledgeItem, SourceRecord
from anki_pipeline.prompt_registry import PromptRegistry
from tests.conftest import MockLLMClient


PROMPTS_DIR = Path(__file__).parent.parent.parent / "src" / "anki_pipeline" / "config" / "prompts"


def _make_chunk(text: str = "The derivative of x^n is nx^{n-1}.") -> Chunk:
    run_id = generate_id()
    return Chunk(
        chunk_id=generate_id(),
        source_id=generate_id(),
        run_id=run_id,
        ordinal=0,
        char_start=0,
        char_end=len(text),
        text=text,
    )


def _make_item(chunk: Chunk, claim: str = "d/dx x^n = nx^{n-1}") -> KnowledgeItem:
    return KnowledgeItem(
        item_id=generate_id(),
        run_id=chunk.run_id,
        source_id=chunk.source_id,
        chunk_id=chunk.chunk_id,
        item_type=KnowledgeItemType.formula,
        claim=claim,
        content_hash=generate_id(),
        deck_target="Math",
    )


class TestAssessGroundingBatch:
    def test_single_item_batch(self):
        chunk = _make_chunk()
        item = _make_item(chunk)
        mock_llm = MockLLMClient({
            BatchGroundingResponse: BatchGroundingResponse(assessments=[
                BatchGroundingItem(claim_index=0, label=AssessmentLabel.direct, score=0.95),
            ]),
        })
        prompts = PromptRegistry(PROMPTS_DIR)

        results = assess_grounding_batch([item], chunk, mock_llm, prompts, run_id=chunk.run_id)

        assert len(results) == 1
        assert results[0].label == AssessmentLabel.direct
        assert results[0].score == 0.95
        assert results[0].knowledge_item_id == item.item_id
        assert results[0].chunk_id == chunk.chunk_id

    def test_multiple_items_batch(self):
        chunk = _make_chunk("The derivative of x^n is nx^{n-1}. The integral of 1/x is ln|x| + C.")
        item1 = _make_item(chunk, "d/dx x^n = nx^{n-1}")
        item2 = _make_item(chunk, "integral of 1/x is ln|x|")

        mock_llm = MockLLMClient({
            BatchGroundingResponse: BatchGroundingResponse(assessments=[
                BatchGroundingItem(claim_index=0, label=AssessmentLabel.direct, score=0.9),
                BatchGroundingItem(claim_index=1, label=AssessmentLabel.direct, score=0.85),
            ]),
        })
        prompts = PromptRegistry(PROMPTS_DIR)

        results = assess_grounding_batch([item1, item2], chunk, mock_llm, prompts, run_id=chunk.run_id)

        assert len(results) == 2
        assert results[0].knowledge_item_id == item1.item_id
        assert results[0].label == AssessmentLabel.direct
        assert results[1].knowledge_item_id == item2.item_id
        assert results[1].label == AssessmentLabel.direct

    def test_missing_claim_index_defaults_unsupported(self):
        """If LLM omits a claim_index, that item defaults to unsupported."""
        chunk = _make_chunk()
        item1 = _make_item(chunk, "claim A")
        item2 = _make_item(chunk, "claim B")

        mock_llm = MockLLMClient({
            BatchGroundingResponse: BatchGroundingResponse(assessments=[
                # Only return assessment for index 0, skip index 1
                BatchGroundingItem(claim_index=0, label=AssessmentLabel.direct, score=0.9),
            ]),
        })
        prompts = PromptRegistry(PROMPTS_DIR)

        results = assess_grounding_batch([item1, item2], chunk, mock_llm, prompts, run_id=chunk.run_id)

        assert len(results) == 2
        assert results[0].label == AssessmentLabel.direct
        assert results[1].label == AssessmentLabel.unsupported
        assert results[1].score == 0.0

    def test_empty_items_returns_empty(self):
        chunk = _make_chunk()
        mock_llm = MockLLMClient({})
        prompts = PromptRegistry(PROMPTS_DIR)

        results = assess_grounding_batch([], chunk, mock_llm, prompts, run_id=chunk.run_id)
        assert results == []

    def test_llm_failure_defaults_all_unsupported(self):
        chunk = _make_chunk()
        item = _make_item(chunk)

        mock_llm = MockLLMClient({})  # No response configured → KeyError
        prompts = PromptRegistry(PROMPTS_DIR)

        results = assess_grounding_batch([item], chunk, mock_llm, prompts, run_id=chunk.run_id)

        assert len(results) == 1
        assert results[0].label == AssessmentLabel.unsupported
        assert results[0].score == 0.0

    def test_evidence_span_located_in_chunk(self):
        text = "The derivative of x^n is nx^{n-1}."
        chunk = _make_chunk(text)
        item = _make_item(chunk)
        evidence = "derivative of x^n"

        mock_llm = MockLLMClient({
            BatchGroundingResponse: BatchGroundingResponse(assessments=[
                BatchGroundingItem(
                    claim_index=0,
                    label=AssessmentLabel.direct,
                    score=0.95,
                    evidence_text=evidence,
                ),
            ]),
        })
        prompts = PromptRegistry(PROMPTS_DIR)

        results = assess_grounding_batch([item], chunk, mock_llm, prompts, run_id=chunk.run_id)

        assert len(results) == 1
        assert len(results[0].evidence_spans) == 1
        span = results[0].evidence_spans[0]
        assert span.text == evidence
        assert text[span.char_start:span.char_end] == evidence

    def test_single_llm_call_for_batch(self):
        """Batch grounding makes exactly 1 structured_call regardless of item count."""
        chunk = _make_chunk()
        items = [_make_item(chunk, f"claim {i}") for i in range(5)]

        mock_llm = MockLLMClient({
            BatchGroundingResponse: BatchGroundingResponse(assessments=[
                BatchGroundingItem(claim_index=i, label=AssessmentLabel.direct, score=0.9)
                for i in range(5)
            ]),
        })
        prompts = PromptRegistry(PROMPTS_DIR)

        assess_grounding_batch(items, chunk, mock_llm, prompts, run_id=chunk.run_id)

        assert len(mock_llm.call_log) == 1


class TestAssessGroundingSingle:
    def test_user_attested_no_llm_call(self):
        """User-attested items skip LLM entirely."""
        chunk = _make_chunk()
        item = KnowledgeItem(
            item_id=generate_id(),
            run_id=chunk.run_id,
            item_type=KnowledgeItemType.definition,
            claim="User said so",
            content_hash=generate_id(),
            deck_target="Math",
            provenance_kind=ProvenanceKind.user_attested,
        )
        source = SourceRecord(
            source_id=generate_id(),
            run_id=chunk.run_id,
            entry_mode=EntryMode.document,
        )
        mock_llm = MockLLMClient({})
        prompts = PromptRegistry(PROMPTS_DIR)

        result = assess_grounding(item, chunk, source, mock_llm, prompts, run_id=chunk.run_id)

        assert result.label == AssessmentLabel.user_attested
        assert result.score is None
        assert len(mock_llm.call_log) == 0
