"""Pipeline configuration (Spec Section 11) via pydantic-settings + YAML."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class StrictConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# Sub-configs
# ---------------------------------------------------------------------------

class ChunkingConfig(StrictConfig):
    min_chunk_tokens: int = 50
    max_chunk_tokens: int = 600
    max_oversize_tolerance_tokens: int = 100
    overlap_tokens: int = 0


class ExtractionConfig(StrictConfig):
    max_items_per_chunk: int = 6
    model: str = "claude-opus-4-6"
    max_tokens: int = 2048


class GroundingConfig(StrictConfig):
    inferential_threshold: float = 0.7
    model: str = "claude-opus-4-6"
    max_tokens: int = 1024


class AllocationConfig(StrictConfig):
    min_claim_tokens: int = 5
    max_claim_tokens: int = 200
    hard_rank_threshold: float = 0.3
    max_new_cards_per_run: int = 50
    max_estimated_cost_per_run: float = 60.0


class ValidationConfig(StrictConfig):
    min_front_chars: int = 10
    max_front_chars: int = 500
    max_back_chars: int = 2000
    max_text_chars: int = 2000


class ExportConfig(StrictConfig):
    output_dir: str = "output"
    method: str = "tsv"  # "tsv" | "direct"
    anki_connect_url: str = "http://localhost:8765"
    anki_connect_timeout: int = 10


class ReviewConfig(StrictConfig):
    show_invalid: bool = False
    editor: str | None = None  # None = use $EDITOR env var


class RankingConfig(StrictConfig):
    weight_importance: float = 0.4
    weight_forgettability: float = 0.3
    weight_testability: float = 0.3
    estimated_card_cost: dict[str, float] = Field(
        default_factory=lambda: {
            "definition": 1.0,
            "mechanism": 1.5,
            "distinction": 2.0,
            "formula": 1.0,
            "procedure": 2.0,
            "exception": 1.0,
            "heuristic": 1.0,
            "unknown": 999.0,
        }
    )
    model: str = "claude-opus-4-6"
    max_tokens: int = 1024


class PipelineConfig(StrictConfig):
    """Top-level pipeline configuration."""
    db_path: str = "pipeline.db"
    model: str = "claude-opus-4-6"
    chunking: ChunkingConfig = Field(default_factory=ChunkingConfig)
    extraction: ExtractionConfig = Field(default_factory=ExtractionConfig)
    grounding: GroundingConfig = Field(default_factory=GroundingConfig)
    allocation: AllocationConfig = Field(default_factory=AllocationConfig)
    validation: ValidationConfig = Field(default_factory=ValidationConfig)
    export: ExportConfig = Field(default_factory=ExportConfig)
    review: ReviewConfig = Field(default_factory=ReviewConfig)
    ranking: RankingConfig = Field(default_factory=RankingConfig)

    @classmethod
    def from_yaml(cls, path: Path) -> "PipelineConfig":
        """Load config from a YAML file."""
        if not path.exists():
            return cls()
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return cls.model_validate(data)

    def config_hash(self) -> str:
        """Deterministic SHA-256 hash of the full effective config."""
        serialized = json.dumps(self.model_dump(), sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


# Default config directory
_DEFAULT_CONFIG_DIR = Path(__file__).parent / "config"


def load_config(config_path: Path | None = None) -> PipelineConfig:
    """Load pipeline config, falling back to defaults."""
    if config_path is None:
        config_path = _DEFAULT_CONFIG_DIR / "pipeline.yaml"
    return PipelineConfig.from_yaml(config_path)
