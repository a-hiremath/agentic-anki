"""Prompt registry - load, hash, and render prompt templates (Spec Section 12)."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class PromptTemplate:
    """A loaded prompt template with version tracking."""
    name: str
    version_hash: str
    content: str

    def render(self, **kwargs: Any) -> str:
        """Render the template by substituting {{key}} placeholders."""
        result = self.content
        for key, value in kwargs.items():
            result = result.replace("{{" + key + "}}", str(value))
        return result


class PromptRegistry:
    """Loads and caches prompt templates from a directory.

    Prompts are `.md` files. The version_hash is SHA-256 of the file content.
    """

    def __init__(self, prompts_dir: Path) -> None:
        self.prompts_dir = prompts_dir
        self._cache: dict[str, PromptTemplate] = {}

    def get(self, name: str) -> PromptTemplate:
        """Load a prompt by name (relative to prompts_dir, without .md extension).

        Example: registry.get("synthesis/definition")
        """
        if name in self._cache:
            return self._cache[name]

        path = self.prompts_dir / f"{name}.md"
        if not path.exists():
            raise FileNotFoundError(f"Prompt not found: {path}")

        content = path.read_text(encoding="utf-8")
        version_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        template = PromptTemplate(name=name, version_hash=version_hash, content=content)
        self._cache[name] = template
        return template

    def effective_hash(self, name: str, config_fragments: list[str]) -> str:
        """Hash including the prompt content and config/taxonomy fragments."""
        template = self.get(name)
        combined = template.content + "\n".join(config_fragments)
        return hashlib.sha256(combined.encode("utf-8")).hexdigest()

    def invalidate(self, name: str | None = None) -> None:
        """Invalidate cache (for testing or live reload)."""
        if name is None:
            self._cache.clear()
        else:
            self._cache.pop(name, None)
