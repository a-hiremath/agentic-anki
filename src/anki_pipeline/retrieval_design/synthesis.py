"""LLM note synthesis, type-dispatched by KnowledgeItemType (Spec Section 15.2)."""

from __future__ import annotations

import json
import logging

from anki_pipeline.enums import KnowledgeItemType, NoteType, ProvenanceKind
from anki_pipeline.identity import generate_id, note_identity_hash
from anki_pipeline.llm.client import LLMClient
from anki_pipeline.llm.schemas import SynthesizedBasicNote, SynthesizedClozeNote
from anki_pipeline.models import EvidenceSpan, KnowledgeItem, NoteCandidate, SynthesisAttempt
from anki_pipeline.normalize import normalize_math_delimiters
from anki_pipeline.prompt_registry import PromptRegistry

logger = logging.getLogger(__name__)

# Type → (prompt name, note type, output schema)
_TYPE_DISPATCH: dict[KnowledgeItemType, tuple[str, NoteType, type]] = {
    KnowledgeItemType.definition:  ("synthesis/definition",  NoteType.stem_basic,  SynthesizedBasicNote),
    KnowledgeItemType.mechanism:   ("synthesis/mechanism",   NoteType.stem_basic,  SynthesizedBasicNote),
    KnowledgeItemType.distinction: ("synthesis/distinction", NoteType.stem_cloze,  SynthesizedClozeNote),
    KnowledgeItemType.formula:     ("synthesis/formula",     NoteType.stem_basic,  SynthesizedBasicNote),
    KnowledgeItemType.procedure:   ("synthesis/procedure",   NoteType.stem_cloze,  SynthesizedClozeNote),
    KnowledgeItemType.exception:   ("synthesis/exception",   NoteType.stem_basic,  SynthesizedBasicNote),
    KnowledgeItemType.heuristic:   ("synthesis/heuristic",   NoteType.stem_basic,  SynthesizedBasicNote),
}


def synthesize_notes(
    item: KnowledgeItem,
    evidence: list[EvidenceSpan],
    llm: LLMClient,
    prompts: PromptRegistry,
    run_id: str,
) -> tuple[list[NoteCandidate], SynthesisAttempt]:
    """Synthesize Anki note candidates from a KnowledgeItem.

    Returns (candidates, attempt). Candidates are NOT written to DB here.
    """
    attempt = SynthesisAttempt(
        attempt_id=generate_id(),
        run_id=run_id,
        knowledge_item_id=item.item_id,
        model_name=llm.model,
    )

    dispatch = _TYPE_DISPATCH.get(item.item_type)
    if dispatch is None:
        attempt.error_message = f"No synthesis strategy for type: {item.item_type.value}"
        return [], attempt

    prompt_name, note_type, schema_class = dispatch
    template = prompts.get(prompt_name)
    attempt.prompt_version = template.version_hash

    # Build evidence text for the prompt
    evidence_text = "\n\n".join(s.text for s in evidence) if evidence else item.claim

    system = f"You are creating a high-quality Anki flashcard for STEM material."
    user = template.render(
        claim=item.claim,
        subject_tag_root=item.subject_tag_root,
        evidence_text=evidence_text,
    )

    try:
        result = llm.structured_call(
            output_schema=schema_class,
            system=system,
            user=user,
            max_tokens=1024,
        )
        raw_response = json.dumps(result.model_dump())
    except Exception as exc:
        logger.error("Synthesis failed for item %s: %s", item.item_id, exc)
        attempt.error_message = str(exc)
        return [], attempt

    attempt.notes_generated = 1

    # Build source field from evidence
    source_field = _build_source_field(evidence, item)

    # Build tags
    tags = _build_tags(item)

    # Build candidate
    if note_type == NoteType.stem_basic:
        assert isinstance(result, SynthesizedBasicNote)
        front = normalize_math_delimiters(result.front)
        back = normalize_math_delimiters(result.back)
        back_extra = normalize_math_delimiters(result.back_extra) if result.back_extra else None
        identity = note_identity_hash(
            NoteType.stem_basic,
            front=front,
            back=back,
            back_extra=back_extra,
        )
        candidate = NoteCandidate(
            candidate_id=generate_id(),
            run_id=run_id,
            knowledge_item_id=item.item_id,
            note_type=NoteType.stem_basic,
            front=front,
            back=back,
            back_extra=back_extra,
            source_field=source_field,
            tags=tags,
            note_identity_hash=identity,
            provenance_kind=item.provenance_kind,
            synthesis_attempt_id=attempt.attempt_id,
        )
    else:
        assert isinstance(result, SynthesizedClozeNote)
        text = normalize_math_delimiters(result.text)
        back_extra = normalize_math_delimiters(result.back_extra) if result.back_extra else None
        identity = note_identity_hash(
            NoteType.stem_cloze,
            text=text,
            back_extra=back_extra,
        )
        candidate = NoteCandidate(
            candidate_id=generate_id(),
            run_id=run_id,
            knowledge_item_id=item.item_id,
            note_type=NoteType.stem_cloze,
            text=text,
            back_extra=back_extra,
            source_field=source_field,
            tags=tags,
            note_identity_hash=identity,
            provenance_kind=item.provenance_kind,
            synthesis_attempt_id=attempt.attempt_id,
        )

    attempt.raw_response = raw_response
    attempt.notes_accepted = 1
    return [candidate], attempt


def _build_source_field(evidence: list[EvidenceSpan], item: KnowledgeItem) -> str:
    if not evidence:
        return ""
    parts = []
    for span in evidence:
        if span.page_or_section:
            parts.append(span.page_or_section)
    return ", ".join(dict.fromkeys(parts))  # deduplicate, preserve order


def _build_tags(item: KnowledgeItem) -> list[str]:
    tags = []
    if item.subject_tag_root:
        tags.append(item.subject_tag_root)
    tags.append(f"type::{item.item_type.value}")
    return tags
