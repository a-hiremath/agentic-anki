"""Content-based identity functions (Spec Section 9.2)."""

import hashlib
import uuid
from pathlib import Path

from anki_pipeline.enums import NoteType
from anki_pipeline.normalize import normalize_for_claim_hash, normalize_for_note_hash, normalize_for_source_hash


def source_fingerprint(canonical_text: str) -> str:
    """SHA-256 of the normalized canonical text of a source document."""
    normalized = normalize_for_source_hash(canonical_text)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def content_hash(item_type: str, claim: str) -> str:
    """SHA-256 of normalized '{item_type}|{claim}'.

    Used for deduplication of KnowledgeItems across ingestions.
    Normalizes type and claim independently so leading/trailing whitespace
    on either part cannot affect the hash.
    """
    norm_type = normalize_for_claim_hash(item_type)
    norm_claim = normalize_for_claim_hash(claim)
    raw = f"{norm_type}|{norm_claim}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def note_identity_hash(note_type: NoteType, **fields: str | None) -> str:
    """Compute a stable identity hash for a note from its semantic fields.

    Type-dispatched:
      STEMBasic:  hash(note_type, front, back, back_extra)
      STEMCloze:  hash(note_type, text, back_extra)

    Fields are normalized via normalize_for_note_hash before hashing.
    """
    def _norm(v: str | None) -> str:
        if v is None:
            return ""
        return normalize_for_note_hash(v)

    if note_type == NoteType.stem_basic:
        parts = [
            note_type.value,
            _norm(fields.get("front")),
            _norm(fields.get("back")),
            _norm(fields.get("back_extra")),
        ]
    elif note_type == NoteType.stem_cloze:
        parts = [
            note_type.value,
            _norm(fields.get("text")),
            _norm(fields.get("back_extra")),
        ]
    else:
        raise ValueError(f"Unknown note_type: {note_type!r}")

    raw = "\x00".join(parts)  # null-byte separator (cannot appear in normalized text)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def file_hash(path: Path) -> str:
    """SHA-256 of the raw bytes of a file."""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def generate_id() -> str:
    """Generate a new UUID4 string."""
    return str(uuid.uuid4())
