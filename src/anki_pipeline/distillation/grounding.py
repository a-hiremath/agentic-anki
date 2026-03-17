"""Evidence localization and grounding assessment (Spec Section 13.4)."""

from __future__ import annotations

import json
import logging

from anki_pipeline.enums import AssessmentLabel, ProvenanceKind
from anki_pipeline.identity import generate_id
from anki_pipeline.llm.client import LLMClient
from anki_pipeline.llm.schemas import BatchGroundingResponse, GroundingResponse
from anki_pipeline.models import Chunk, EvidenceSpan, GroundingAssessment, KnowledgeItem, SourceRecord
from anki_pipeline.prompt_registry import PromptRegistry

logger = logging.getLogger(__name__)


def assess_grounding(
    item: KnowledgeItem,
    chunk: Chunk,
    source: SourceRecord,
    llm: LLMClient,
    prompts: PromptRegistry,
    run_id: str,
) -> GroundingAssessment:
    """Assess grounding of a KnowledgeItem against its source chunk.

    Mode A (document): LLM adjudicates support level.
    Mode B (concept/user_attested): No LLM call; record user_attested.
    """
    if item.provenance_kind == ProvenanceKind.user_attested:
        return _user_attested_assessment(item, run_id)

    return _document_assessment(item, chunk, llm, prompts, run_id)


def _user_attested_assessment(item: KnowledgeItem, run_id: str) -> GroundingAssessment:
    """Mode B: user-attested concept, no LLM call, no numeric score."""
    return GroundingAssessment(
        assessment_id=generate_id(),
        run_id=run_id,
        knowledge_item_id=item.item_id,
        chunk_id=None,
        label=AssessmentLabel.user_attested,
        score=None,  # never fabricate a numeric score
        evidence_spans=[],
        prompt_version="",
        model_name="",
    )


def _document_assessment(
    item: KnowledgeItem,
    chunk: Chunk,
    llm: LLMClient,
    prompts: PromptRegistry,
    run_id: str,
    max_tokens: int = 512,
) -> GroundingAssessment:
    """Mode A: LLM-based grounding assessment against source chunk."""
    template = prompts.get("grounding")
    system = "You are an evidence assessor determining whether a claim is supported by a source text."
    claims_json = json.dumps([{"index": 0, "item_type": item.item_type.value, "claim": item.claim}])
    user = template.render(
        chunk_text=chunk.text,
        claims_json=claims_json,
    )

    try:
        response: GroundingResponse = llm.structured_call(
            output_schema=GroundingResponse,
            system=system,
            user=user,
            max_tokens=max_tokens,
        )
    except Exception as exc:
        logger.error("Grounding failed for item %s: %s", item.item_id, exc)
        # Default to unsupported on failure
        return GroundingAssessment(
            assessment_id=generate_id(),
            run_id=run_id,
            knowledge_item_id=item.item_id,
            chunk_id=chunk.chunk_id,
            label=AssessmentLabel.unsupported,
            score=0.0,
            prompt_version=template.version_hash,
            model_name=llm.model,
        )

    spans = []
    if response.evidence_text and response.label in (AssessmentLabel.direct, AssessmentLabel.inferential):
        # Locate evidence text in chunk
        ev_text = response.evidence_text
        idx = chunk.text.find(ev_text)
        if idx >= 0:
            span = EvidenceSpan(
                span_id=generate_id(),
                knowledge_item_id=item.item_id,
                chunk_id=chunk.chunk_id,
                char_start=idx,
                char_end=idx + len(ev_text),
                text=ev_text,
                page_or_section=chunk.heading_path,
            )
            spans.append(span)

    return GroundingAssessment(
        assessment_id=generate_id(),
        run_id=run_id,
        knowledge_item_id=item.item_id,
        chunk_id=chunk.chunk_id,
        label=response.label,
        score=response.score,
        evidence_spans=spans,
        prompt_version=template.version_hash,
        model_name=llm.model,
    )


def assess_grounding_batch(
    items: list[KnowledgeItem],
    chunk: Chunk,
    llm: LLMClient,
    prompts: PromptRegistry,
    run_id: str,
    max_tokens: int = 512,
) -> list[GroundingAssessment]:
    """Assess grounding of multiple items from the same chunk in a single LLM call."""
    if not items:
        return []

    template = prompts.get("grounding")
    system = "You are an evidence assessor determining whether a claim is supported by a source text."
    claims = [
        {"index": i, "item_type": item.item_type.value, "claim": item.claim}
        for i, item in enumerate(items)
    ]
    user = template.render(chunk_text=chunk.text, claims_json=json.dumps(claims))

    try:
        response: BatchGroundingResponse = llm.structured_call(
            output_schema=BatchGroundingResponse,
            system=system,
            user=user,
            max_tokens=max_tokens,
        )
    except Exception as exc:
        logger.error("Batch grounding failed for chunk %s: %s", chunk.chunk_id, exc)
        return [
            GroundingAssessment(
                assessment_id=generate_id(),
                run_id=run_id,
                knowledge_item_id=item.item_id,
                chunk_id=chunk.chunk_id,
                label=AssessmentLabel.unsupported,
                score=0.0,
                prompt_version=template.version_hash,
                model_name=llm.model,
            )
            for item in items
        ]

    # Index response assessments by claim_index for fast lookup
    response_map = {a.claim_index: a for a in response.assessments}

    results: list[GroundingAssessment] = []
    for i, item in enumerate(items):
        assessed = response_map.get(i)
        if assessed is None:
            # LLM omitted this item — default to unsupported
            results.append(GroundingAssessment(
                assessment_id=generate_id(),
                run_id=run_id,
                knowledge_item_id=item.item_id,
                chunk_id=chunk.chunk_id,
                label=AssessmentLabel.unsupported,
                score=0.0,
                prompt_version=template.version_hash,
                model_name=llm.model,
            ))
            continue

        spans = []
        if assessed.evidence_text and assessed.label in (AssessmentLabel.direct, AssessmentLabel.inferential):
            idx = chunk.text.find(assessed.evidence_text)
            if idx >= 0:
                spans.append(EvidenceSpan(
                    span_id=generate_id(),
                    knowledge_item_id=item.item_id,
                    chunk_id=chunk.chunk_id,
                    char_start=idx,
                    char_end=idx + len(assessed.evidence_text),
                    text=assessed.evidence_text,
                    page_or_section=chunk.heading_path,
                ))

        results.append(GroundingAssessment(
            assessment_id=generate_id(),
            run_id=run_id,
            knowledge_item_id=item.item_id,
            chunk_id=chunk.chunk_id,
            label=assessed.label,
            score=assessed.score,
            evidence_spans=spans,
            prompt_version=template.version_hash,
            model_name=llm.model,
        ))

    return results
