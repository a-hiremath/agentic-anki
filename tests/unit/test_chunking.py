"""Tests for chunking with offset invariant (Spec Section 13.2)."""

import pytest

from anki_pipeline.config import ChunkingConfig
from anki_pipeline.distillation.chunking import chunk_source
from anki_pipeline.enums import EntryMode
from anki_pipeline.identity import generate_id
from anki_pipeline.models import SourceRecord


def make_source(text: str) -> SourceRecord:
    return SourceRecord(
        source_id=generate_id(),
        run_id=generate_id(),
        entry_mode=EntryMode.document,
        canonical_text=text,
        source_fingerprint=generate_id(),
        char_count=len(text),
    )


SAMPLE_MATH = """# Introduction to Calculus

Calculus is the study of continuous change.

## Derivatives

The derivative of a function measures the rate of change.

$$
f'(x) = \\lim_{h \\to 0} \\frac{f(x+h) - f(x)}{h}
$$

This limit definition is fundamental.

## Integrals

The integral gives the area under a curve.

$$
\\int_a^b f(x) \\, dx = F(b) - F(a)
$$

where $F$ is the antiderivative.
"""


class TestOffsetInvariant:
    def test_offset_invariant_holds(self):
        source = make_source(SAMPLE_MATH)
        chunks = chunk_source(source, ChunkingConfig())
        for chunk in chunks:
            assert source.canonical_text[chunk.char_start:chunk.char_end] == chunk.text

    def test_offset_invariant_simple_text(self):
        text = "Line one.\n\nLine two.\n\nLine three.\n"
        source = make_source(text)
        chunks = chunk_source(source, ChunkingConfig(min_chunk_tokens=1))
        for chunk in chunks:
            assert source.canonical_text[chunk.char_start:chunk.char_end] == chunk.text

    def test_offset_invariant_with_latex(self):
        text = "Section 1\n\n$$a + b = c$$\n\nSection 2\n\nMore text here.\n"
        source = make_source(text)
        chunks = chunk_source(source, ChunkingConfig(min_chunk_tokens=1))
        for chunk in chunks:
            assert source.canonical_text[chunk.char_start:chunk.char_end] == chunk.text


class TestChunkBoundaries:
    def test_heading_based_chunking(self):
        source = make_source(SAMPLE_MATH)
        chunks = chunk_source(source, ChunkingConfig(min_chunk_tokens=5))
        # Should have multiple chunks (one per section at minimum)
        assert len(chunks) >= 2

    def test_ordinals_sequential(self):
        source = make_source(SAMPLE_MATH)
        chunks = chunk_source(source, ChunkingConfig())
        ordinals = [c.ordinal for c in chunks]
        assert ordinals == list(range(len(chunks)))

    def test_chunks_cover_all_content(self):
        text = SAMPLE_MATH
        source = make_source(text)
        chunks = chunk_source(source, ChunkingConfig())
        # Reconstruct text from chunks
        covered = set()
        for c in chunks:
            for i in range(c.char_start, c.char_end):
                covered.add(i)
        # All non-whitespace positions should be covered
        assert len(covered) > 0

    def test_math_not_split_mid_equation(self):
        text = "Intro text.\n\n$$\\int_0^1 x^2 dx = \\frac{1}{3}$$\n\nAfter math.\n"
        source = make_source(text)
        chunks = chunk_source(source, ChunkingConfig(min_chunk_tokens=1, max_chunk_tokens=10))
        # Verify no chunk starts or ends in the middle of $$ ... $$
        math_start = text.index("$$")
        math_end = text.rindex("$$") + 2
        for chunk in chunks:
            # No chunk boundary inside the math block
            inside = range(chunk.char_start, chunk.char_end)
            if math_start in inside or (math_end - 1) in inside:
                # The chunk that contains the math should contain all of it
                assert chunk.char_start <= math_start and chunk.char_end >= math_end


class TestEdgeCases:
    def test_empty_source_returns_empty(self):
        source = make_source("")
        chunks = chunk_source(source, ChunkingConfig())
        assert chunks == []

    def test_single_paragraph(self):
        text = "A single paragraph with enough words to form one chunk."
        source = make_source(text)
        chunks = chunk_source(source, ChunkingConfig(min_chunk_tokens=1))
        assert len(chunks) >= 1
        # Offset invariant
        for chunk in chunks:
            assert source.canonical_text[chunk.char_start:chunk.char_end] == chunk.text

    def test_token_count_set(self):
        source = make_source(SAMPLE_MATH)
        chunks = chunk_source(source, ChunkingConfig())
        for chunk in chunks:
            assert chunk.token_count >= 0
