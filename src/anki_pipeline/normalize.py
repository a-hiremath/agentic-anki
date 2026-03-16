"""Text normalization functions (Spec Section 9.1).

Each normalizer is purpose-built; do NOT mix normalizers between purposes.
"""

import re
import unicodedata


# Zero-width and invisible characters to strip
_ZERO_WIDTH_CHARS = re.compile(
    r"[\u200b\u200c\u200d\u200e\u200f\u00ad\ufeff\u2060\u2061\u2062\u2063]"
)
_WHITESPACE_RUN = re.compile(r"[ \t\r\n]+")
_TRAILING_WHITESPACE_LINE = re.compile(r"[ \t]+$", re.MULTILINE)


def normalize_for_claim_hash(text: str) -> str:
    """Normalize text for content_hash computation.

    - NFC unicode normalization
    - Strip BOM
    - Remove zero-width chars
    - Collapse all whitespace runs to single space
    - Strip leading/trailing whitespace
    - Lowercase
    """
    text = text.lstrip("\ufeff")  # strip BOM
    text = unicodedata.normalize("NFC", text)
    text = _ZERO_WIDTH_CHARS.sub("", text)
    text = _WHITESPACE_RUN.sub(" ", text)
    text = text.strip()
    text = text.lower()
    return text


def normalize_for_note_hash(text: str) -> str:
    """Normalize text for note_identity_hash computation.

    Preserves LaTeX/math formatting exactly; only strips BOM and zero-width chars.
    Does NOT lowercase — math is case-sensitive.
    """
    text = text.lstrip("\ufeff")  # strip BOM
    text = unicodedata.normalize("NFC", text)
    text = _ZERO_WIDTH_CHARS.sub("", text)
    # Collapse non-math whitespace runs but preserve newlines (they may matter in math)
    text = re.sub(r"[ \t]+", " ", text)
    text = text.strip()
    return text


def normalize_for_source_hash(text: str) -> str:
    """Normalize text for source_fingerprint computation.

    - NFC unicode normalization
    - Strip BOM
    - Normalize line endings to \\n
    - Strip trailing whitespace from each line
    - Normalize final newline
    """
    text = text.lstrip("\ufeff")  # strip BOM
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _TRAILING_WHITESPACE_LINE.sub("", text)
    text = text.rstrip("\n") + "\n"  # single trailing newline
    return text


def normalize_cosmetic(text: str) -> str:
    """Normalize text for edit-type detection (cosmetic vs semantic).

    Strips punctuation differences, whitespace differences, and case differences
    so that only semantic content changes survive.
    """
    text = text.lstrip("\ufeff")
    text = unicodedata.normalize("NFC", text)
    text = _ZERO_WIDTH_CHARS.sub("", text)
    # Collapse whitespace
    text = _WHITESPACE_RUN.sub(" ", text)
    text = text.strip()
    # Strip leading/trailing punctuation from tokens
    text = re.sub(r"[^\w\s]", "", text)
    text = text.lower()
    return text
