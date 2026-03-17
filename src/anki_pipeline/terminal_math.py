"""Terminal-only LaTeX rendering helpers for review UX."""

from __future__ import annotations

import logging
import re
from functools import lru_cache
from typing import Any

from anki_pipeline.normalize import normalize_math_delimiters

logger = logging.getLogger(__name__)

_MATH_BLOCK = re.compile(r"\\\((?P<inline>.+?)\\\)|\\\[(?P<display>.+?)\\\]", re.DOTALL)


def render_latex_for_terminal(text: str | None) -> str:
    """Convert MathJax-style LaTeX fragments into readable terminal text.

    This is display-only. Stored note content remains unchanged.
    """
    if not text:
        return ""

    normalized = normalize_math_delimiters(text)
    converter = _get_converter()
    if converter is None:
        return normalized

    return _MATH_BLOCK.sub(lambda match: _render_match(match, converter), normalized)


@lru_cache(maxsize=1)
def _get_converter() -> Any | None:
    try:
        from pylatexenc.latex2text import LatexNodes2Text
    except ImportError:
        logger.debug("pylatexenc not installed; leaving LaTeX source unchanged in review UI")
        return None
    return LatexNodes2Text()


def _render_match(match: re.Match[str], converter: Any) -> str:
    latex = match.group("inline") if match.group("inline") is not None else match.group("display")
    try:
        rendered = converter.latex_to_text(latex).strip()
    except Exception:
        logger.debug("Failed to render terminal math for %r", latex, exc_info=True)
        return match.group(0)
    return rendered or match.group(0)
