"""File ingestion: read, normalize, fingerprint source documents (Spec Section 13.1)."""

from __future__ import annotations

import logging
from pathlib import Path

from anki_pipeline.enums import EntryMode
from anki_pipeline.identity import file_hash, generate_id, source_fingerprint
from anki_pipeline.models import SourceRecord

logger = logging.getLogger(__name__)

_SUPPORTED_TYPES = {
    ".pdf": "application/pdf",
    ".md": "text/markdown",
    ".txt": "text/plain",
    ".tex": "text/x-latex",
}


def _detect_media_type(path: Path) -> str:
    return _SUPPORTED_TYPES.get(path.suffix.lower(), "text/plain")


def _read_pdf(path: Path) -> str:
    """Extract markdown text from a PDF using pymupdf4llm."""
    try:
        import pymupdf4llm  # type: ignore[import]
        return pymupdf4llm.to_markdown(str(path))
    except ImportError as exc:
        raise ImportError(
            "pymupdf4llm is required for PDF ingestion. Install it with: pip install pymupdf4llm"
        ) from exc


def _read_text(path: Path) -> str:
    """Read a text/markdown file, stripping BOM."""
    raw = path.read_bytes()
    # Strip UTF-8 BOM if present
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    return raw.decode("utf-8", errors="replace")


def ingest_source(
    file_path: Path,
    run_id: str,
    media_type: str | None = None,
) -> SourceRecord:
    """Ingest a source file and return a SourceRecord.

    Does NOT write to the database — caller is responsible for dedup check and persistence.
    """
    if not file_path.exists():
        raise FileNotFoundError(f"Source file not found: {file_path}")

    detected_type = media_type or _detect_media_type(file_path)
    raw_hash = file_hash(file_path)

    if detected_type == "application/pdf":
        canonical_text = _read_pdf(file_path)
    else:
        canonical_text = _read_text(file_path)

    fp = source_fingerprint(canonical_text)

    return SourceRecord(
        source_id=generate_id(),
        run_id=run_id,
        entry_mode=EntryMode.document,
        file_path=str(file_path.resolve()),
        media_type=detected_type,
        raw_file_hash=raw_hash,
        source_fingerprint=fp,
        canonical_text=canonical_text,
        char_count=len(canonical_text),
    )
