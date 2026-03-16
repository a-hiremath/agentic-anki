"""Tests for prompt registry."""

import pytest
from pathlib import Path

from anki_pipeline.prompt_registry import PromptRegistry, PromptTemplate


def test_load_prompt(prompts_dir: Path):
    registry = PromptRegistry(prompts_dir)
    template = registry.get("extraction")
    assert template.name == "extraction"
    assert len(template.version_hash) == 64  # SHA-256 hex
    assert "{{chunk_text}}" in template.content


def test_hash_stability(prompts_dir: Path):
    registry = PromptRegistry(prompts_dir)
    t1 = registry.get("extraction")
    registry.invalidate("extraction")
    t2 = registry.get("extraction")
    assert t1.version_hash == t2.version_hash


def test_render_substitution(prompts_dir: Path):
    registry = PromptRegistry(prompts_dir)
    template = registry.get("extraction")
    rendered = template.render(
        max_items="6",
        subject="math",
        deck_target="Math::Calc",
        chunk_text="The derivative is a limit.",
    )
    assert "6" in rendered
    assert "Math::Calc" in rendered
    assert "The derivative is a limit." in rendered


def test_missing_prompt_raises(tmp_path: Path):
    registry = PromptRegistry(tmp_path)
    with pytest.raises(FileNotFoundError):
        registry.get("nonexistent_prompt")


def test_synthesis_prompts_loadable(prompts_dir: Path):
    registry = PromptRegistry(prompts_dir)
    for name in ["definition", "mechanism", "distinction", "formula", "procedure", "exception", "heuristic"]:
        template = registry.get(f"synthesis/{name}")
        assert "{{claim}}" in template.content


def test_effective_hash_includes_config(prompts_dir: Path):
    registry = PromptRegistry(prompts_dir)
    h1 = registry.effective_hash("extraction", ["config_fragment_a"])
    h2 = registry.effective_hash("extraction", ["config_fragment_b"])
    assert h1 != h2


def test_cache_works(prompts_dir: Path):
    registry = PromptRegistry(prompts_dir)
    t1 = registry.get("extraction")
    t2 = registry.get("extraction")
    assert t1 is t2  # same object from cache
