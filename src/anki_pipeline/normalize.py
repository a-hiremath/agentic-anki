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
_CODE_SPAN_OR_FENCE = re.compile(r"(```.*?```|`[^`\n]*`)", re.DOTALL)
_MATH_SIGNAL = re.compile(r"(\\[A-Za-z]+|[\^_{}=<>+\-*/()])")


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


def normalize_math_delimiters(text: str) -> str:
    """Convert dollar-delimited math into Anki-native MathJax delimiters.

    Rules:
    - `$$...$$` -> `\\[...\\]`
    - `$...$` -> `\\(...\\)` when the enclosed content looks like math
    - Leave escaped dollars and code spans/fences untouched
    - Avoid converting obvious currency-like prose such as "$100 and $200"
    """
    if "$" not in text:
        return text

    parts: list[str] = []
    last = 0
    for match in _CODE_SPAN_OR_FENCE.finditer(text):
        parts.append(_normalize_math_segment(text[last:match.start()]))
        parts.append(match.group(0))
        last = match.end()
    parts.append(_normalize_math_segment(text[last:]))
    return "".join(parts)


def has_raw_math_dollar_delimiters(text: str) -> bool:
    """Return True when the text still contains convertible raw dollar math."""
    return normalize_math_delimiters(text) != text


def _normalize_math_segment(text: str) -> str:
    return _normalize_inline_math(_normalize_display_math(text))


def _normalize_display_math(text: str) -> str:
    out: list[str] = []
    i = 0
    while i < len(text):
        if _starts_unescaped(text, i, "$$"):
            end = _find_matching_double_dollar(text, i + 2)
            if end != -1:
                out.append(r"\[" + text[i + 2:end] + r"\]")
                i = end + 2
                continue
        out.append(text[i])
        i += 1
    return "".join(out)


def _normalize_inline_math(text: str) -> str:
    out: list[str] = []
    i = 0
    while i < len(text):
        if _is_single_dollar(text, i):
            end = _find_matching_single_dollar(text, i + 1)
            if end != -1:
                content = text[i + 1:end]
                if _should_convert_inline_math(content):
                    out.append(r"\(" + content + r"\)")
                    i = end + 1
                    continue
        out.append(text[i])
        i += 1
    return "".join(out)


def _should_convert_inline_math(content: str) -> bool:
    stripped = content.strip()
    if not stripped:
        return False
    if "\n" in stripped:
        return False
    if " " in stripped and not _MATH_SIGNAL.search(stripped):
        return False
    return True


def _find_matching_double_dollar(text: str, start: int) -> int:
    i = start
    while i < len(text) - 1:
        if _starts_unescaped(text, i, "$$"):
            return i
        i += 1
    return -1


def _find_matching_single_dollar(text: str, start: int) -> int:
    i = start
    while i < len(text):
        if _is_single_dollar(text, i):
            return i
        i += 1
    return -1


def _starts_unescaped(text: str, index: int, token: str) -> bool:
    return text.startswith(token, index) and not _is_escaped(text, index)


def _is_single_dollar(text: str, index: int) -> bool:
    if index >= len(text) or text[index] != "$" or _is_escaped(text, index):
        return False
    if index > 0 and text[index - 1] == "$":
        return False
    if index + 1 < len(text) and text[index + 1] == "$":
        return False
    return True


def _is_escaped(text: str, index: int) -> bool:
    backslashes = 0
    i = index - 1
    while i >= 0 and text[i] == "\\":
        backslashes += 1
        i -= 1
    return backslashes % 2 == 1
