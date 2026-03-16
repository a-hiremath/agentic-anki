"""Rule-based chunking with offset tracking (Spec Section 13.2).

Critical invariant: canonical_text[chunk.char_start:chunk.char_end] == chunk.text
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from pathlib import Path

from anki_pipeline.config import ChunkingConfig
from anki_pipeline.identity import generate_id
from anki_pipeline.models import Chunk, SourceRecord

logger = logging.getLogger(__name__)

# Patterns for structural boundaries (ordered by priority)
_MD_HEADING = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
_LATEX_SECTION = re.compile(
    r"^\\(section|subsection|subsubsection|chapter)\{([^}]+)\}", re.MULTILINE
)
_THEOREM_BLOCK = re.compile(
    r"^\\begin\{(theorem|definition|proof|lemma|corollary|proposition|remark|example)\}",
    re.MULTILINE,
)
_DOUBLE_NEWLINE = re.compile(r"\n{2,}")

# Math block patterns — never split inside these
_DISPLAY_MATH_DOUBLE = re.compile(r"\$\$.*?\$\$", re.DOTALL)
_DISPLAY_MATH_BRACKET = re.compile(r"\\\[.*?\\\]", re.DOTALL)
_LATEX_EQUATION = re.compile(r"\\begin\{(equation|align|gather|multline)\*?\}.*?\\end\{\1\*?\}", re.DOTALL)


def _approximate_tokens(text: str) -> int:
    """Rough token count: number of whitespace-separated words."""
    return len(text.split())


def _find_math_spans(text: str) -> list[tuple[int, int]]:
    """Return list of (start, end) for all display math regions that must not be split."""
    spans: list[tuple[int, int]] = []
    for pattern in (_DISPLAY_MATH_DOUBLE, _DISPLAY_MATH_BRACKET, _LATEX_EQUATION):
        for m in pattern.finditer(text):
            spans.append((m.start(), m.end()))
    # Sort and merge overlapping
    spans.sort()
    merged: list[tuple[int, int]] = []
    for s, e in spans:
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    return merged


def _in_math_span(pos: int, math_spans: list[tuple[int, int]]) -> bool:
    for s, e in math_spans:
        if s <= pos < e:
            return True
    return False


def _find_boundaries(text: str) -> list[int]:
    """Find candidate split positions (offsets where a new chunk could start).

    Returns positions sorted ascending, not inside math blocks.
    """
    math_spans = _find_math_spans(text)
    positions: set[int] = set()

    # Markdown headings
    for m in _MD_HEADING.finditer(text):
        pos = m.start()
        if not _in_math_span(pos, math_spans):
            positions.add(pos)

    # LaTeX sectioning
    for m in _LATEX_SECTION.finditer(text):
        pos = m.start()
        if not _in_math_span(pos, math_spans):
            positions.add(pos)

    # Theorem/definition blocks
    for m in _THEOREM_BLOCK.finditer(text):
        pos = m.start()
        if not _in_math_span(pos, math_spans):
            positions.add(pos)

    # Paragraph breaks (double newlines)
    for m in _DOUBLE_NEWLINE.finditer(text):
        pos = m.end()  # start of next paragraph
        if pos < len(text) and not _in_math_span(pos, math_spans):
            positions.add(pos)

    return sorted(positions)


def _extract_heading_path(text: str) -> str:
    """Extract the first heading from a text chunk as a path string."""
    m = _MD_HEADING.search(text)
    if m:
        return m.group(2).strip()
    m = _LATEX_SECTION.search(text)
    if m:
        return m.group(2).strip()
    return ""


def chunk_source(source: SourceRecord, config: ChunkingConfig) -> list[Chunk]:
    """Split a SourceRecord into chunks with correct offset tracking.

    The critical invariant is maintained:
        source.canonical_text[chunk.char_start:chunk.char_end] == chunk.text
    """
    text = source.canonical_text
    if not text:
        return []

    boundaries = _find_boundaries(text)
    # Add text start and end as anchors
    all_positions = sorted({0} | set(boundaries) | {len(text)})

    # Build raw segments
    raw_segments: list[tuple[int, int]] = []
    for i in range(len(all_positions) - 1):
        start = all_positions[i]
        end = all_positions[i + 1]
        if start < end:
            raw_segments.append((start, end))

    if not raw_segments:
        raw_segments = [(0, len(text))]

    # Merge micro-chunks and split oversized
    chunks = _merge_and_split(raw_segments, text, config)

    # Build Chunk objects with correct offsets
    result: list[Chunk] = []
    for ordinal, (start, end) in enumerate(chunks):
        chunk_text = text[start:end]
        # Verify invariant (defensive)
        assert text[start:end] == chunk_text, "Chunk offset invariant violated"
        result.append(
            Chunk(
                chunk_id=generate_id(),
                source_id=source.source_id,
                run_id=source.run_id,
                ordinal=ordinal,
                char_start=start,
                char_end=end,
                text=chunk_text,
                token_count=_approximate_tokens(chunk_text),
                heading_path=_extract_heading_path(chunk_text),
            )
        )

    logger.debug(
        "Chunked source_id=%s into %d chunks (total_chars=%d)",
        source.source_id, len(result), len(text)
    )
    return result


def _merge_and_split(
    segments: list[tuple[int, int]],
    text: str,
    config: ChunkingConfig,
) -> list[tuple[int, int]]:
    """Merge micro-chunks below min_chunk_tokens; split oversized above max_chunk_tokens."""
    math_spans = _find_math_spans(text)
    max_with_tolerance = config.max_chunk_tokens + config.max_oversize_tolerance_tokens

    # First pass: merge micro-chunks
    merged: list[tuple[int, int]] = []
    for start, end in segments:
        chunk_text = text[start:end]
        tokens = _approximate_tokens(chunk_text)
        if merged and tokens < config.min_chunk_tokens:
            # Merge with previous
            prev_start, _ = merged[-1]
            merged[-1] = (prev_start, end)
        else:
            merged.append((start, end))

    # Second pass: split oversized chunks (but not mid-math)
    final: list[tuple[int, int]] = []
    for start, end in merged:
        chunk_text = text[start:end]
        tokens = _approximate_tokens(chunk_text)
        if tokens <= max_with_tolerance:
            final.append((start, end))
        else:
            # Split at sentence boundaries
            sub = _split_at_sentences(start, end, text, config.max_chunk_tokens, math_spans)
            final.extend(sub)

    return final


def _split_at_sentences(
    start: int,
    end: int,
    text: str,
    max_tokens: int,
    math_spans: list[tuple[int, int]],
) -> list[tuple[int, int]]:
    """Split a large segment at sentence boundaries, respecting math spans."""
    sentence_end = re.compile(r"(?<=[.!?])\s+")
    segments: list[tuple[int, int]] = []
    current_start = start
    current_tokens = 0

    for m in sentence_end.finditer(text, start, end):
        split_pos = m.end()
        if _in_math_span(split_pos, math_spans):
            continue
        tokens_so_far = _approximate_tokens(text[current_start:split_pos])
        if tokens_so_far >= max_tokens and split_pos > current_start:
            segments.append((current_start, split_pos))
            current_start = split_pos
            current_tokens = 0

    # Remainder
    if current_start < end:
        segments.append((current_start, end))

    return segments if segments else [(start, end)]
