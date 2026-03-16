"""Response parsing utilities for the Anthropic API."""

from __future__ import annotations

import json
from typing import Any


def extract_tool_use_input(response: Any) -> dict[str, Any]:
    """Extract the input dict from the first tool_use block in a response.

    Raises ValueError if no tool_use block is found.
    """
    for block in response.content:
        if block.type == "tool_use":
            return block.input  # type: ignore[no-any-return]
    raise ValueError("No tool_use block found in LLM response")


def response_to_text(response: Any) -> str:
    """Extract all text blocks from a response as a single string."""
    parts = []
    for block in response.content:
        if block.type == "text":
            parts.append(block.text)
    return "\n".join(parts)
