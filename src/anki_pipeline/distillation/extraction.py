"""LLM extraction of KnowledgeItems from chunks (Spec Section 13.3)."""

from __future__ import annotations

import json
import logging
from typing import Any

from anki_pipeline.config import ExtractionConfig
from anki_pipeline.enums import ProvenanceKind
from anki_pipeline.identity import content_hash, generate_id
from anki_pipeline.llm.client import LLMClient
from anki_pipeline.llm.schemas import ExtractionResponse
from anki_pipeline.models import Chunk, ExtractionAttempt, KnowledgeItem, SourceRecord
from anki_pipeline.prompt_registry import PromptRegistry

logger = logging.getLogger(__name__)


def extract_from_chunk(
    chunk: Chunk,
    source: SourceRecord,
    llm: LLMClient,
    prompts: PromptRegistry,
    config: ExtractionConfig,
    run_id: str,
    deck_target: str,
) -> tuple[list[KnowledgeItem], ExtractionAttempt]:
    """Extract KnowledgeItems from a single chunk via LLM.

    Returns (items, attempt). Items are NOT written to DB here.
    """
    template = prompts.get("extraction")

    system = (
        "You are an expert STEM knowledge extractor. Extract atomic, testable knowledge items."
    )
    user = template.render(
        max_items=str(config.max_items_per_chunk),
        subject=source.file_path or "Unknown",
        deck_target=deck_target,
        chunk_text=chunk.text,
    )

    attempt = ExtractionAttempt(
        attempt_id=generate_id(),
        run_id=run_id,
        chunk_id=chunk.chunk_id,
        prompt_version=template.version_hash,
        model_name=llm.model,
    )

    try:
        response: ExtractionResponse = llm.structured_call(
            output_schema=ExtractionResponse,
            system=system,
            user=user,
            max_tokens=config.max_tokens,
        )
        raw_items = response.items[: config.max_items_per_chunk]
        attempt.items_extracted = len(raw_items)
        attempt.raw_response = json.dumps([i.model_dump() for i in raw_items])
    except Exception as exc:
        logger.error("Extraction failed for chunk %s: %s", chunk.chunk_id, exc)
        attempt.error_message = str(exc)
        return [], attempt

    items: list[KnowledgeItem] = []
    for extracted in raw_items:
        ch = content_hash(extracted.item_type.value, extracted.claim)
        item = KnowledgeItem(
            item_id=generate_id(),
            run_id=run_id,
            source_id=source.source_id,
            chunk_id=chunk.chunk_id,
            item_type=extracted.item_type,
            claim=extracted.claim,
            content_hash=ch,
            deck_target=deck_target,
            provenance_kind=ProvenanceKind.source_extracted,
            subject_tag_root="",
            why_memorable=extracted.why_memorable,
        )
        items.append(item)

    attempt.items_accepted = len(items)
    return items, attempt
