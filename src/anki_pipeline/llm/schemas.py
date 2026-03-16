"""Pydantic models for LLM request/response schemas."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from anki_pipeline.enums import AssessmentLabel, KnowledgeItemType


class StrictLLMModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# Extraction schemas
# ---------------------------------------------------------------------------

class ExtractedItem(StrictLLMModel):
    item_type: KnowledgeItemType
    claim: str
    why_memorable: str | None = None


class ExtractionResponse(StrictLLMModel):
    items: list[ExtractedItem]


# ---------------------------------------------------------------------------
# Grounding schemas
# ---------------------------------------------------------------------------

class GroundingResponse(StrictLLMModel):
    label: AssessmentLabel
    score: float = Field(ge=0.0, le=1.0)
    evidence_text: str | None = None
    reasoning: str | None = None


# ---------------------------------------------------------------------------
# Ranking schemas
# ---------------------------------------------------------------------------

class RankedItem(StrictLLMModel):
    item_id: str
    importance: float = Field(ge=0.0, le=1.0)
    forgettability: float = Field(ge=0.0, le=1.0)
    testability: float = Field(ge=0.0, le=1.0)


class RankingResponse(StrictLLMModel):
    rankings: list[RankedItem]


# ---------------------------------------------------------------------------
# Synthesis schemas
# ---------------------------------------------------------------------------

class SynthesizedBasicNote(StrictLLMModel):
    front: str
    back: str
    back_extra: str | None = None


class SynthesizedClozeNote(StrictLLMModel):
    text: str  # must contain {{c1::...}}
    back_extra: str | None = None
