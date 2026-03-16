"""Tests for enumerations (Spec Section 8.1)."""

import pytest

from anki_pipeline.enums import (
    AssessmentLabel,
    EditType,
    EntryMode,
    KnowledgeItemType,
    NoteType,
    ProvenanceKind,
    ReviewDecision,
    RunStage,
    RunStatus,
    SelectionReason,
)


def test_entry_mode_values():
    assert EntryMode.document.value == "document"
    assert EntryMode.concept.value == "concept"


def test_provenance_kind_roundtrip():
    for member in ProvenanceKind:
        assert ProvenanceKind(member.value) is member


def test_knowledge_item_type_all_present():
    expected = {
        "definition", "mechanism", "distinction", "formula",
        "procedure", "exception", "heuristic", "unknown",
    }
    actual = {m.value for m in KnowledgeItemType}
    assert actual == expected


def test_note_type_values():
    assert NoteType.stem_basic.value == "STEMBasic"
    assert NoteType.stem_cloze.value == "STEMCloze"


def test_invalid_enum_value_raises():
    with pytest.raises(ValueError):
        EntryMode("invalid_value")


def test_all_enums_are_str_subclass():
    for enum_cls in (
        EntryMode, ProvenanceKind, KnowledgeItemType, RunStage,
        AssessmentLabel, ReviewDecision, EditType, NoteType,
        RunStatus, SelectionReason,
    ):
        for member in enum_cls:
            assert isinstance(member, str)
            assert isinstance(member.value, str)


def test_assessment_label_values():
    labels = {m.value for m in AssessmentLabel}
    assert "direct" in labels
    assert "inferential" in labels
    assert "unsupported" in labels
    assert "user_attested" in labels


def test_selection_reason_values():
    reasons = {m.value for m in SelectionReason}
    assert "selected" in reasons
    assert "budget_exhausted" in reasons
    assert "below_threshold" in reasons
    assert "duplicate" in reasons
