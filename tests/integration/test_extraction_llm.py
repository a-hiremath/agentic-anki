"""Integration tests for LLM extraction (require ANTHROPIC_API_KEY)."""

import os
import pytest

from anki_pipeline.config import ExtractionConfig
from anki_pipeline.distillation.extraction import extract_from_chunk
from anki_pipeline.enums import EntryMode
from anki_pipeline.identity import generate_id
from anki_pipeline.llm.client import LLMClient
from anki_pipeline.models import Chunk, SourceRecord
from anki_pipeline.prompt_registry import PromptRegistry
from pathlib import Path


@pytest.mark.llm
def test_extraction_on_math_chunk():
    """Real LLM call: extract items from a small math chunk."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        pytest.skip("ANTHROPIC_API_KEY not set")

    chunk_text = (
        "The derivative of $f(x) = x^n$ is $f'(x) = nx^{n-1}$. "
        "This power rule applies for all real $n$. "
        "The chain rule states that $(f \\circ g)'(x) = f'(g(x)) \\cdot g'(x)$."
    )

    source = SourceRecord(
        source_id=generate_id(),
        run_id=generate_id(),
        entry_mode=EntryMode.document,
        canonical_text=chunk_text,
        source_fingerprint=generate_id(),
        char_count=len(chunk_text),
    )
    chunk = Chunk(
        chunk_id=generate_id(),
        source_id=source.source_id,
        run_id=source.run_id,
        ordinal=0,
        char_start=0,
        char_end=len(chunk_text),
        text=chunk_text,
    )

    llm = LLMClient(api_key=api_key)
    prompts = PromptRegistry(
        Path(__file__).parent.parent.parent / "src" / "anki_pipeline" / "config" / "prompts"
    )
    config = ExtractionConfig(max_items_per_chunk=3)

    items, attempt = extract_from_chunk(
        chunk, source, llm, prompts, config, run_id=source.run_id, deck_target="Math"
    )

    assert attempt.error_message is None
    assert len(items) >= 1
    for item in items:
        assert item.claim
        assert item.content_hash
        assert item.item_type.value in [
            "definition", "mechanism", "distinction", "formula",
            "procedure", "exception", "heuristic", "unknown"
        ]
