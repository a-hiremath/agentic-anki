"""All Pydantic models for the Anki pipeline (Spec Sections 8.1-8.16)."""

from __future__ import annotations

import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

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


class StrictModel(BaseModel):
    """Base model with extra='forbid' to catch typos in field names."""
    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# Spec 8.2 — PipelineRun
# ---------------------------------------------------------------------------

class PipelineRun(StrictModel):
    """Represents a single pipeline execution."""
    run_id: str
    entry_mode: EntryMode
    deck_target: str
    status: RunStatus = RunStatus.running
    trigger: str = "manual"  # "manual" | "rerun"
    config_version: str = ""
    started_at: datetime.datetime = Field(default_factory=datetime.datetime.utcnow)
    finished_at: datetime.datetime | None = None
    error_message: str | None = None
    stages_completed: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Spec 8.3 — SourceRecord
# ---------------------------------------------------------------------------

class SourceRecord(StrictModel):
    """Represents an ingested source document or concept."""
    source_id: str
    run_id: str
    entry_mode: EntryMode
    file_path: str | None = None
    media_type: str = "text/plain"
    raw_file_hash: str | None = None
    source_fingerprint: str = ""
    canonical_text: str = ""
    char_count: int = 0
    created_at: datetime.datetime = Field(default_factory=datetime.datetime.utcnow)


# ---------------------------------------------------------------------------
# Spec 8.4 — Chunk
# ---------------------------------------------------------------------------

class Chunk(StrictModel):
    """A contiguous, semantically coherent region of a source document."""
    chunk_id: str
    source_id: str
    run_id: str
    ordinal: int
    char_start: int
    char_end: int
    text: str
    token_count: int = 0
    heading_path: str = ""  # e.g. "Chapter 1 > Section 2"


# ---------------------------------------------------------------------------
# Spec 8.5 — EvidenceSpan
# ---------------------------------------------------------------------------

class EvidenceSpan(StrictModel):
    """A specific span of text within a chunk that supports a claim."""
    span_id: str
    knowledge_item_id: str
    chunk_id: str
    char_start: int  # relative to chunk text
    char_end: int
    text: str
    page_or_section: str = ""


# ---------------------------------------------------------------------------
# Spec 8.6 — KnowledgeItem
# ---------------------------------------------------------------------------

class KnowledgeItem(StrictModel):
    """An atomic, testable piece of domain knowledge."""
    item_id: str
    run_id: str
    source_id: str | None = None
    chunk_id: str | None = None
    item_type: KnowledgeItemType
    claim: str
    content_hash: str = ""
    deck_target: str = ""
    provenance_kind: ProvenanceKind = ProvenanceKind.source_extracted
    subject_tag_root: str = ""
    why_memorable: str | None = None
    is_active: bool = True
    is_duplicate: bool = False
    created_at: datetime.datetime = Field(default_factory=datetime.datetime.utcnow)


# ---------------------------------------------------------------------------
# Spec 8.7 — ExtractionAttempt
# ---------------------------------------------------------------------------

class ExtractionAttempt(StrictModel):
    """Records a single LLM extraction call."""
    attempt_id: str
    run_id: str
    chunk_id: str
    prompt_version: str = ""
    model_name: str = ""
    items_extracted: int = 0
    items_accepted: int = 0
    items_duplicate: int = 0
    raw_response: str = ""
    error_message: str | None = None
    created_at: datetime.datetime = Field(default_factory=datetime.datetime.utcnow)


# ---------------------------------------------------------------------------
# Spec 8.8 — GroundingAssessment
# ---------------------------------------------------------------------------

class GroundingAssessment(StrictModel):
    """Records grounding support for a KnowledgeItem."""
    assessment_id: str
    run_id: str
    knowledge_item_id: str
    chunk_id: str | None = None
    label: AssessmentLabel
    score: float | None = None  # 0.0-1.0; null for user_attested
    evidence_spans: list[EvidenceSpan] = Field(default_factory=list)
    prompt_version: str = ""
    model_name: str = ""
    created_at: datetime.datetime = Field(default_factory=datetime.datetime.utcnow)


# ---------------------------------------------------------------------------
# Spec 8.9 — RankingAssessment
# ---------------------------------------------------------------------------

class RankingAssessment(StrictModel):
    """Scores a KnowledgeItem on importance, forgettability, testability."""
    ranking_id: str
    run_id: str
    knowledge_item_id: str
    importance: float = 0.0
    forgettability: float = 0.0
    testability: float = 0.0
    aggregate_score: float = 0.0
    estimated_card_cost: float = 1.0
    utility_density: float = 0.0
    prompt_version: str = ""
    model_name: str = ""
    created_at: datetime.datetime = Field(default_factory=datetime.datetime.utcnow)


# ---------------------------------------------------------------------------
# Spec 8.10 — SelectionDecision
# ---------------------------------------------------------------------------

class SelectionDecision(StrictModel):
    """Records whether/why a KnowledgeItem was selected for note generation."""
    decision_id: str
    run_id: str
    knowledge_item_id: str
    selected: bool
    reason: SelectionReason
    budget_snapshot: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime.datetime = Field(default_factory=datetime.datetime.utcnow)


# ---------------------------------------------------------------------------
# Spec 8.11 — NoteCandidate
# ---------------------------------------------------------------------------

class NoteCandidate(StrictModel):
    """A generated but not-yet-reviewed Anki note candidate."""
    candidate_id: str
    run_id: str
    knowledge_item_id: str
    note_type: NoteType
    # STEMBasic fields
    front: str | None = None
    back: str | None = None
    # STEMCloze fields
    text: str | None = None
    # Shared
    back_extra: str | None = None
    source_field: str = ""
    tags: list[str] = Field(default_factory=list)
    note_identity_hash: str = ""
    provenance_kind: ProvenanceKind = ProvenanceKind.source_extracted
    synthesis_attempt_id: str = ""
    created_at: datetime.datetime = Field(default_factory=datetime.datetime.utcnow)


# ---------------------------------------------------------------------------
# Spec 8.12 — SynthesisAttempt
# ---------------------------------------------------------------------------

class SynthesisAttempt(StrictModel):
    """Records a single LLM synthesis call."""
    attempt_id: str
    run_id: str
    knowledge_item_id: str
    prompt_version: str = ""
    model_name: str = ""
    notes_generated: int = 0
    notes_accepted: int = 0
    raw_response: str = ""
    error_message: str | None = None
    created_at: datetime.datetime = Field(default_factory=datetime.datetime.utcnow)


# ---------------------------------------------------------------------------
# Spec 8.13 — ValidationResult
# ---------------------------------------------------------------------------

class ValidationResult(StrictModel):
    """Result of deterministic validation for a NoteCandidate."""
    result_id: str
    candidate_id: str
    run_id: str
    passed: bool
    failure_codes: list[str] = Field(default_factory=list)
    warning_codes: list[str] = Field(default_factory=list)
    created_at: datetime.datetime = Field(default_factory=datetime.datetime.utcnow)


# ---------------------------------------------------------------------------
# Spec 8.14 — ReviewAction
# ---------------------------------------------------------------------------

class ReviewAction(StrictModel):
    """Records a human review action on a NoteCandidate."""
    action_id: str
    run_id: str
    candidate_id: str
    decision: ReviewDecision
    edit_type: EditType | None = None
    edited_fields: dict[str, str] = Field(default_factory=dict)
    reject_reason_code: str | None = None
    reviewer_notes: str | None = None
    created_at: datetime.datetime = Field(default_factory=datetime.datetime.utcnow)


# ---------------------------------------------------------------------------
# Spec 8.15 — ReviewedNote
# ---------------------------------------------------------------------------

class ReviewedNote(StrictModel):
    """A note that has passed human review and is ready for export."""
    reviewed_note_id: str
    run_id: str
    candidate_id: str
    action_id: str
    note_type: NoteType
    # Fields (same as candidate, possibly edited)
    front: str | None = None
    back: str | None = None
    text: str | None = None
    back_extra: str | None = None
    source_field: str = ""
    tags: list[str] = Field(default_factory=list)
    note_identity_hash: str = ""
    provenance_kind: ProvenanceKind
    ready_for_export: bool = True
    created_at: datetime.datetime = Field(default_factory=datetime.datetime.utcnow)


# ---------------------------------------------------------------------------
# Spec 8.16 — ExportRecord
# ---------------------------------------------------------------------------

class ExportRecord(StrictModel):
    """Records a successful export of a ReviewedNote."""
    export_id: str
    reviewed_note_id: str
    run_id: str
    deck_target: str
    tsv_row: str = ""
    export_method: str = "tsv"
    status: str = "success"  # "success" | "skipped" | "failed"
    output_file: str = ""
    created_at: datetime.datetime = Field(default_factory=datetime.datetime.utcnow)
