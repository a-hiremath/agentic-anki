"""Deterministic rule-based validation of note candidates (Spec Section 15.3).

No LLM calls. Every note produces a ValidationResult, even when passing.
"""

from __future__ import annotations

import re
import logging

from anki_pipeline.config import ValidationConfig
from anki_pipeline.enums import NoteType
from anki_pipeline.identity import generate_id
from anki_pipeline.models import NoteCandidate, ValidationResult

logger = logging.getLogger(__name__)

_CLOZE_PATTERN = re.compile(r"\{\{c\d+::.+?\}\}")
_VAGUE_PRONOUN = re.compile(r"^(it |this |they |these |those )", re.IGNORECASE)
_TAG_VALID = re.compile(r"^[a-zA-Z0-9_:./-]+$")


def validate_note(note: NoteCandidate, config: ValidationConfig) -> ValidationResult:
    """Run all deterministic validation checks on a NoteCandidate.

    Returns ValidationResult. `passed=True` if no hard failures.
    """
    failures: list[str] = []
    warnings: list[str] = []

    if note.note_type == NoteType.stem_basic:
        _validate_basic(note, config, failures, warnings)
    elif note.note_type == NoteType.stem_cloze:
        _validate_cloze(note, config, failures, warnings)
    else:
        failures.append(f"invalid_note_type:{note.note_type!r}")

    # Tag validation
    for tag in note.tags:
        if not _TAG_VALID.match(tag):
            failures.append(f"invalid_tag:{tag!r}")

    # Source field check (warning only)
    if not note.source_field and note.provenance_kind.value != "user_attested":
        warnings.append("missing_source_field")

    passed = len(failures) == 0

    return ValidationResult(
        result_id=generate_id(),
        candidate_id=note.candidate_id,
        run_id=note.run_id,
        passed=passed,
        failure_codes=failures,
        warning_codes=warnings,
    )


def _validate_basic(
    note: NoteCandidate,
    config: ValidationConfig,
    failures: list[str],
    warnings: list[str],
) -> None:
    # Required fields
    if not note.front or not note.front.strip():
        failures.append("empty_front")
        return  # no point checking length on empty

    if not note.back or not note.back.strip():
        failures.append("empty_back")
        return

    front = note.front.strip()
    back = note.back.strip()

    # Length checks
    if len(front) < config.min_front_chars:
        failures.append(f"front_too_short:{len(front)}<{config.min_front_chars}")
    if len(front) > config.max_front_chars:
        failures.append(f"front_too_long:{len(front)}>{config.max_front_chars}")
    if len(back) > config.max_back_chars:
        failures.append(f"back_too_long:{len(back)}>{config.max_back_chars}")

    # Warnings
    if _VAGUE_PRONOUN.match(front):
        warnings.append("vague_pronoun_front")


def _validate_cloze(
    note: NoteCandidate,
    config: ValidationConfig,
    failures: list[str],
    warnings: list[str],
) -> None:
    # Required field
    if not note.text or not note.text.strip():
        failures.append("empty_text")
        return

    text = note.text.strip()

    # Must contain at least one cloze
    if not _CLOZE_PATTERN.search(text):
        failures.append("missing_cloze_syntax")

    # Length
    if len(text) > config.max_text_chars:
        failures.append(f"text_too_long:{len(text)}>{config.max_text_chars}")

    # Warnings
    if _VAGUE_PRONOUN.match(text):
        warnings.append("vague_pronoun_text")
