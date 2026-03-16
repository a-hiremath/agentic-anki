"""Tests for text normalization functions (Spec Section 9.1)."""

import pytest

from anki_pipeline.normalize import (
    normalize_cosmetic,
    normalize_for_claim_hash,
    normalize_for_note_hash,
    normalize_for_source_hash,
)


class TestNormalizeForClaimHash:
    def test_strips_bom(self):
        assert normalize_for_claim_hash("\ufeffhello") == "hello"

    def test_nfc_normalization(self):
        # é as two code points (e + combining acute) → NFC é (single code point)
        import unicodedata
        decomposed = "e\u0301"
        composed = unicodedata.normalize("NFC", decomposed)
        assert normalize_for_claim_hash(decomposed) == normalize_for_claim_hash(composed)

    def test_collapses_whitespace(self):
        assert normalize_for_claim_hash("hello   world\t\nfoo") == "hello world foo"

    def test_strips_zero_width_chars(self):
        assert normalize_for_claim_hash("hel\u200blo") == "hello"
        assert normalize_for_claim_hash("hel\u200clo") == "hello"

    def test_lowercase(self):
        assert normalize_for_claim_hash("HELLO WORLD") == "hello world"

    def test_strip_leading_trailing(self):
        assert normalize_for_claim_hash("  hello  ") == "hello"

    def test_empty_string(self):
        assert normalize_for_claim_hash("") == ""


class TestNormalizeForNoteHash:
    def test_preserves_case(self):
        result = normalize_for_note_hash("Hello World $E=mc^2$")
        assert "Hello" in result
        assert "World" in result

    def test_strips_bom(self):
        assert normalize_for_note_hash("\ufeffHello") == "Hello"

    def test_preserves_latex(self):
        latex = "The formula $\\frac{d}{dx}[x^n] = nx^{n-1}$ is important."
        result = normalize_for_note_hash(latex)
        assert "\\frac" in result
        assert "nx^{n-1}" in result

    def test_strips_zero_width(self):
        assert normalize_for_note_hash("hel\u200blo") == "hello"


class TestNormalizeForSourceHash:
    def test_normalizes_crlf(self):
        assert normalize_for_source_hash("line1\r\nline2") == "line1\nline2\n"

    def test_normalizes_cr(self):
        assert normalize_for_source_hash("line1\rline2") == "line1\nline2\n"

    def test_strips_trailing_whitespace_per_line(self):
        assert normalize_for_source_hash("hello   \nworld  \n") == "hello\nworld\n"

    def test_single_trailing_newline(self):
        result = normalize_for_source_hash("hello\n\n\n")
        assert result.endswith("\n")
        assert result.rstrip("\n") == "hello"

    def test_strips_bom(self):
        assert normalize_for_source_hash("\ufeffhello") == "hello\n"

    def test_deterministic(self):
        text = "Some source text\n\nWith paragraphs.\n"
        assert normalize_for_source_hash(text) == normalize_for_source_hash(text)


class TestNormalizeCosmetic:
    def test_strips_punctuation(self):
        result = normalize_cosmetic("Hello, World!")
        assert "," not in result
        assert "!" not in result

    def test_lowercases(self):
        assert normalize_cosmetic("HELLO") == "hello"

    def test_collapses_whitespace(self):
        assert normalize_cosmetic("  hello   world  ") == "hello world"

    def test_same_semantic_content_different_punctuation(self):
        a = normalize_cosmetic("Hello, world!")
        b = normalize_cosmetic("Hello world")
        assert a == b
