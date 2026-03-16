"""Tests for allocation scoring."""

import pytest

from anki_pipeline.allocation.scoring import score_items
from anki_pipeline.config import RankingConfig
from anki_pipeline.enums import KnowledgeItemType, ProvenanceKind
from anki_pipeline.identity import generate_id
from anki_pipeline.llm.schemas import RankedItem, RankingResponse
from anki_pipeline.models import KnowledgeItem


def make_item(item_type=KnowledgeItemType.definition) -> KnowledgeItem:
    return KnowledgeItem(
        item_id=generate_id(),
        run_id="run1",
        item_type=item_type,
        claim="Some claim about the topic.",
        content_hash=generate_id(),
        deck_target="Math",
    )


class TestScoreItems:
    def test_weighted_sum_computed_correctly(self):
        item = make_item()
        config = RankingConfig(
            weight_importance=0.4,
            weight_forgettability=0.3,
            weight_testability=0.3,
        )
        from tests.conftest import MockLLMClient
        from anki_pipeline.llm.schemas import RankingResponse, RankedItem

        mock = MockLLMClient({
            RankingResponse: RankingResponse(rankings=[
                RankedItem(
                    item_id=item.item_id,
                    importance=0.8,
                    forgettability=0.6,
                    testability=0.9,
                )
            ])
        })

        from anki_pipeline.prompt_registry import PromptRegistry
        from pathlib import Path
        prompts = PromptRegistry(
            Path(__file__).parent.parent.parent / "src" / "anki_pipeline" / "config" / "prompts"
        )

        results = score_items([item], "run1", mock, prompts, config, "Math")
        assert len(results) == 1
        r = results[0]

        expected_aggregate = 0.4 * 0.8 + 0.3 * 0.6 + 0.3 * 0.9
        assert abs(r.aggregate_score - expected_aggregate) < 1e-6

    def test_utility_density_is_aggregate_over_cost(self):
        item = make_item(item_type=KnowledgeItemType.distinction)
        config = RankingConfig()
        cost = config.estimated_card_cost["distinction"]  # 2.0

        from tests.conftest import MockLLMClient
        mock = MockLLMClient({
            RankingResponse: RankingResponse(rankings=[
                RankedItem(item_id=item.item_id, importance=0.6, forgettability=0.6, testability=0.6)
            ])
        })

        from anki_pipeline.prompt_registry import PromptRegistry
        from pathlib import Path
        prompts = PromptRegistry(
            Path(__file__).parent.parent.parent / "src" / "anki_pipeline" / "config" / "prompts"
        )
        results = score_items([item], "run1", mock, prompts, config, "Math")
        r = results[0]
        expected_density = r.aggregate_score / cost
        assert abs(r.utility_density - expected_density) < 1e-6

    def test_empty_input_returns_empty(self):
        from tests.conftest import MockLLMClient
        config = RankingConfig()
        results = score_items([], "run1", MockLLMClient({}), None, config)  # type: ignore
        assert results == []

    def test_fallback_to_default_on_llm_error(self):
        """When LLM call fails, items get default 0.5 scores."""
        item = make_item()
        config = RankingConfig()
        from tests.conftest import MockLLMClient
        # Mock that raises an error
        class FailingLLM(MockLLMClient):
            def structured_call(self, *a, **kw):
                raise RuntimeError("LLM unavailable")
            model = "mock"

        from anki_pipeline.prompt_registry import PromptRegistry
        from pathlib import Path
        prompts = PromptRegistry(
            Path(__file__).parent.parent.parent / "src" / "anki_pipeline" / "config" / "prompts"
        )
        results = score_items([item], "run1", FailingLLM({}), prompts, config)
        assert len(results) == 1
        # Default fallback is 0.5 for all dimensions
        r = results[0]
        assert r.importance == 0.5
        assert r.forgettability == 0.5
        assert r.testability == 0.5
