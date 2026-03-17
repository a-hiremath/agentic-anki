"""Shared test fixtures and mock helpers."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from anki_pipeline.config import PipelineConfig
from anki_pipeline.storage import Database


@pytest.fixture
def tmp_db(tmp_path: Path) -> Database:
    """Return a fresh in-memory-like Database backed by a temp file."""
    return Database(tmp_path / "test.db")


@pytest.fixture
def tmp_path_factory_dir(tmp_path: Path) -> Path:
    return tmp_path


class MockLLMClient:
    """Mock LLM client for testing.

    Stores canned responses by output schema type.
    """

    def __init__(self, responses: dict[type, Any]) -> None:
        self.responses = responses
        self.call_log: list[tuple[type, str, str]] = []
        self.model = "mock-model"

    def structured_call(
        self, output_schema: type, system: str, user: str, **kwargs: Any
    ) -> Any:
        self.call_log.append((output_schema, system, user))
        if output_schema not in self.responses:
            raise KeyError(f"No mock response for {output_schema.__name__}")
        return self.responses[output_schema]

    def usage_summary(self) -> dict[str, int]:
        return {"total_input_tokens": 0, "total_output_tokens": 0, "total_calls": len(self.call_log)}


@pytest.fixture
def mock_llm() -> MockLLMClient:
    """Return a MockLLMClient with empty responses (test sets them up)."""
    return MockLLMClient({})


@pytest.fixture
def default_config() -> PipelineConfig:
    return PipelineConfig()


@pytest.fixture
def prompts_dir() -> Path:
    """Return the real prompts directory from the package."""
    return Path(__file__).parent.parent / "src" / "anki_pipeline" / "config" / "prompts"
