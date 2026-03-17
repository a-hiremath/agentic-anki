"""Tests for deterministic note validation (Spec Section 15.3)."""

import pytest

from anki_pipeline.config import ValidationConfig
from anki_pipeline.enums import NoteType, ProvenanceKind
from anki_pipeline.identity import generate_id
from anki_pipeline.models import NoteCandidate
from anki_pipeline.retrieval_design.validation import validate_note


def make_basic(front="What is a derivative?", back="The instantaneous rate of change.", **kwargs) -> NoteCandidate:
    return NoteCandidate(
        candidate_id=generate_id(),
        run_id="run1",
        knowledge_item_id=generate_id(),
        note_type=NoteType.stem_basic,
        front=front,
        back=back,
        **kwargs,
    )


def make_cloze(text="The derivative of \\(x^n\\) is {{c1::\\(nx^{n-1}\\)}}.", **kwargs) -> NoteCandidate:
    return NoteCandidate(
        candidate_id=generate_id(),
        run_id="run1",
        knowledge_item_id=generate_id(),
        note_type=NoteType.stem_cloze,
        text=text,
        **kwargs,
    )


config = ValidationConfig()


class TestBasicValidation:
    def test_valid_note_passes(self):
        result = validate_note(make_basic(), config)
        assert result.passed
        assert result.failure_codes == []

    def test_empty_front_fails(self):
        result = validate_note(make_basic(front=""), config)
        assert not result.passed
        assert "empty_front" in result.failure_codes

    def test_empty_back_fails(self):
        result = validate_note(make_basic(back=""), config)
        assert not result.passed
        assert "empty_back" in result.failure_codes

    def test_front_too_short_fails(self):
        result = validate_note(make_basic(front="Hi"), config)
        assert not result.passed
        assert any("front_too_short" in code for code in result.failure_codes)

    def test_front_too_long_fails(self):
        long_front = "x" * 600
        result = validate_note(make_basic(front=long_front), config)
        assert not result.passed
        assert any("front_too_long" in code for code in result.failure_codes)

    def test_back_too_long_fails(self):
        long_back = "x" * 2100
        result = validate_note(make_basic(back=long_back), config)
        assert not result.passed
        assert any("back_too_long" in code for code in result.failure_codes)

    def test_vague_pronoun_warning(self):
        result = validate_note(make_basic(front="It represents the rate of change."), config)
        assert result.passed  # warning, not failure
        assert "vague_pronoun_front" in result.warning_codes

    def test_raw_dollar_math_is_warning_not_failure(self):
        result = validate_note(make_basic(back="The formula is $x^2$."), config)
        assert result.passed
        assert "raw_math_delimiters_back" in result.warning_codes


class TestClozeValidation:
    def test_valid_cloze_passes(self):
        result = validate_note(make_cloze(), config)
        assert result.passed
        assert result.failure_codes == []

    def test_missing_cloze_syntax_fails(self):
        result = validate_note(make_cloze(text="No cloze here."), config)
        assert not result.passed
        assert "missing_cloze_syntax" in result.failure_codes

    def test_empty_text_fails(self):
        result = validate_note(make_cloze(text=""), config)
        assert not result.passed
        assert "empty_text" in result.failure_codes

    def test_text_too_long_fails(self):
        long_text = "{{c1::x}}" + "y" * 2100
        result = validate_note(make_cloze(text=long_text), config)
        assert not result.passed
        assert any("text_too_long" in code for code in result.failure_codes)

    def test_currency_does_not_trigger_math_warning(self):
        result = validate_note(make_cloze(text="The fee is {{c1::$100}} per attempt."), config)
        assert result.passed
        assert "raw_math_delimiters_text" not in result.warning_codes


class TestTagValidation:
    def test_invalid_tag_fails(self):
        candidate = make_basic(tags=["valid_tag", "invalid tag with spaces"])
        result = validate_note(candidate, config)
        assert not result.passed
        assert any("invalid_tag" in code for code in result.failure_codes)

    def test_valid_tags_pass(self):
        candidate = make_basic(tags=["math.calc1c", "type::definition"])
        result = validate_note(candidate, config)
        assert result.passed


class TestValidationResult:
    def test_always_produces_result(self):
        for candidate in [make_basic(), make_cloze()]:
            result = validate_note(candidate, config)
            assert result is not None
            assert result.candidate_id == candidate.candidate_id
