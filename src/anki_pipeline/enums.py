"""All enumerations for the Anki pipeline (Spec Section 8.1)."""

from enum import Enum


class EntryMode(str, Enum):
    """How a pipeline run was initiated."""
    document = "document"
    concept = "concept"


class ProvenanceKind(str, Enum):
    """Provenance of a knowledge item or note."""
    source_extracted = "source_extracted"
    user_attested = "user_attested"
    human_edited = "human_edited"
    mixed = "mixed"


class KnowledgeItemType(str, Enum):
    """Semantic type of extracted knowledge."""
    definition = "definition"
    mechanism = "mechanism"
    distinction = "distinction"
    formula = "formula"
    procedure = "procedure"
    exception = "exception"
    heuristic = "heuristic"
    unknown = "unknown"


class RunStage(str, Enum):
    """Pipeline stage identifiers."""
    ingestion = "ingestion"
    chunking = "chunking"
    extraction = "extraction"
    grounding = "grounding"
    filtering = "filtering"
    scoring = "scoring"
    selection = "selection"
    synthesis = "synthesis"
    validation = "validation"
    review = "review"
    export = "export"


class AssessmentLabel(str, Enum):
    """Grounding support label."""
    direct = "direct"
    inferential = "inferential"
    unsupported = "unsupported"
    user_attested = "user_attested"


class ReviewDecision(str, Enum):
    """Human review decision for a note candidate."""
    accept = "accept"
    reject = "reject"
    edit = "edit"
    skip = "skip"


class EditType(str, Enum):
    """Type of edit made during review."""
    cosmetic = "cosmetic"
    semantic = "semantic"


class NoteType(str, Enum):
    """Anki note type."""
    stem_basic = "STEMBasic"
    stem_cloze = "STEMCloze"


class RunStatus(str, Enum):
    """Overall pipeline run status."""
    running = "running"
    completed = "completed"
    failed = "failed"
    partial = "partial"


class SelectionReason(str, Enum):
    """Reason for a selection decision."""
    selected = "selected"
    below_threshold = "below_threshold"
    budget_exhausted = "budget_exhausted"
    duplicate = "duplicate"
    unsupported = "unsupported"
    invalid = "invalid"
    unknown_type = "unknown_type"
    token_bounds = "token_bounds"
    invalid_provenance = "invalid_provenance"
