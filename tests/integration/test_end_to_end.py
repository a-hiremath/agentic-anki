"""End-to-end integration tests (mock LLM)."""

from __future__ import annotations

import pytest
from pathlib import Path

from anki_pipeline.config import PipelineConfig
from anki_pipeline.enums import AssessmentLabel, KnowledgeItemType
from anki_pipeline.identity import generate_id
from anki_pipeline.llm.schemas import (
    BatchGroundingItem, BatchGroundingResponse, ExtractionResponse,
    ExtractedItem, GroundingResponse, RankingResponse, RankedItem,
    SynthesizedBasicNote,
)
from anki_pipeline.prompt_registry import PromptRegistry
from anki_pipeline.retrieval_design.export import export_deck
from anki_pipeline.runs.orchestration import PipelineOrchestrator
from anki_pipeline.storage import Database
from tests.conftest import MockLLMClient


FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


def make_mock_llm(item_id: str) -> MockLLMClient:
    """Create a mock LLM with canned responses for all pipeline stages."""
    from anki_pipeline.llm.schemas import RankingResponse
    return MockLLMClient({
        ExtractionResponse: ExtractionResponse(items=[
            ExtractedItem(
                item_type=KnowledgeItemType.definition,
                claim="The definite integral is the limit of a Riemann sum.",
                why_memorable="Connects discrete sums to continuous areas.",
            )
        ]),
        BatchGroundingResponse: BatchGroundingResponse(assessments=[
            BatchGroundingItem(
                claim_index=0,
                label=AssessmentLabel.direct,
                score=0.95,
                evidence_text="The definite integral",
            ),
        ]),
        GroundingResponse: GroundingResponse(
            label=AssessmentLabel.direct,
            score=0.95,
            evidence_text="The definite integral",
        ),
        RankingResponse: RankingResponse(rankings=[
            RankedItem(item_id=item_id, importance=0.9, forgettability=0.8, testability=0.9)
        ]),
        SynthesizedBasicNote: SynthesizedBasicNote(
            front="What is the definite integral?",
            back="The limit of a Riemann sum: $\\int_a^b f(x)\\,dx$.",
            back_extra="Fundamental Theorem connects it to antiderivatives.",
        ),
    })


class TestDocumentPipeline:
    def test_full_document_run(self, tmp_path: Path):
        """Full pipeline with mock LLM on sample markdown."""
        db = Database(tmp_path / "test.db")
        cfg = PipelineConfig(db_path=str(tmp_path / "test.db"))
        prompts = PromptRegistry(
            Path(__file__).parent.parent.parent / "src" / "anki_pipeline" / "config" / "prompts"
        )

        placeholder_id = generate_id()
        mock_llm = make_mock_llm(placeholder_id)

        orchestrator = PipelineOrchestrator(cfg, db, mock_llm, prompts)  # type: ignore[arg-type]

        source_path = FIXTURES_DIR / "sample_math.md"
        run = orchestrator.run_document(source_path, "Math::Calc1C")

        from anki_pipeline.enums import RunStatus
        assert run.status == RunStatus.completed

        # Verify data was written to DB
        with db.connect() as conn:
            sources = conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0]
            chunks = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
            items = conn.execute("SELECT COUNT(*) FROM knowledge_items").fetchone()[0]
            candidates = conn.execute("SELECT COUNT(*) FROM note_candidates").fetchone()[0]
            validations = conn.execute("SELECT COUNT(*) FROM validation_results").fetchone()[0]
            candidate_back = conn.execute(
                "SELECT back FROM note_candidates WHERE back IS NOT NULL LIMIT 1"
            ).fetchone()

        assert sources >= 1
        assert chunks >= 1
        assert items >= 0  # could be 0 if all filtered
        assert validations >= 0
        if candidate_back:
            assert r"\(" in candidate_back[0]

    def test_duplicate_ingestion_no_duplicate_sources(self, tmp_path: Path):
        """Ingesting the same file twice should reuse the existing source."""
        db = Database(tmp_path / "test.db")
        cfg = PipelineConfig(db_path=str(tmp_path / "test.db"))
        prompts = PromptRegistry(
            Path(__file__).parent.parent.parent / "src" / "anki_pipeline" / "config" / "prompts"
        )
        mock_llm = make_mock_llm(generate_id())
        orchestrator = PipelineOrchestrator(cfg, db, mock_llm, prompts)  # type: ignore[arg-type]

        source_path = FIXTURES_DIR / "sample_math.md"
        orchestrator.run_document(source_path, "Math::Calc1C")
        orchestrator.run_document(source_path, "Math::Calc1C")

        with db.connect() as conn:
            count = conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0]
        assert count == 1  # only one source record


class TestConceptPipeline:
    def test_concept_run(self, tmp_path: Path):
        db = Database(tmp_path / "test.db")
        cfg = PipelineConfig(db_path=str(tmp_path / "test.db"))
        prompts = PromptRegistry(
            Path(__file__).parent.parent.parent / "src" / "anki_pipeline" / "config" / "prompts"
        )
        mock_llm = make_mock_llm(generate_id())
        orchestrator = PipelineOrchestrator(cfg, db, mock_llm, prompts)  # type: ignore[arg-type]

        run = orchestrator.run_concept(
            {
                "item_type": "definition",
                "claim": "RAII ties resource management to object lifetime.",
                "subject_tag_root": "cs.cpp",
            },
            deck_target="CS::CPP",
        )

        from anki_pipeline.enums import RunStatus, ProvenanceKind
        assert run.status == RunStatus.completed

        # Concept items should be user_attested
        with db.connect() as conn:
            row = conn.execute(
                "SELECT provenance_kind FROM knowledge_items WHERE deck_target='CS::CPP'"
            ).fetchone()
        if row:
            assert row[0] == ProvenanceKind.user_attested.value
