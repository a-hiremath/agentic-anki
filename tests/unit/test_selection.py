"""Tests for budget-constrained selection (Spec Section 14.3)."""

import pytest

from anki_pipeline.allocation.selection import select_within_budget
from anki_pipeline.config import AllocationConfig
from anki_pipeline.enums import SelectionReason
from anki_pipeline.identity import generate_id
from anki_pipeline.models import RankingAssessment


def make_ranking(
    aggregate_score=0.8, cost=1.0, utility_density=None
) -> RankingAssessment:
    ud = utility_density if utility_density is not None else aggregate_score / cost
    return RankingAssessment(
        ranking_id=generate_id(),
        run_id="run1",
        knowledge_item_id=generate_id(),
        importance=0.8,
        forgettability=0.7,
        testability=0.9,
        aggregate_score=aggregate_score,
        estimated_card_cost=cost,
        utility_density=ud,
    )


class TestSelectWithinBudget:
    def test_selects_until_budget_full(self):
        config = AllocationConfig(
            max_new_cards_per_run=3,
            max_estimated_cost_per_run=3.0,
        )
        rankings = [make_ranking(cost=1.0) for _ in range(10)]
        decisions = select_within_budget(rankings, config)
        selected = [d for d in decisions if d.selected]
        assert len(selected) == 3

    def test_all_get_decision(self):
        config = AllocationConfig(max_new_cards_per_run=5, max_estimated_cost_per_run=5.0)
        rankings = [make_ranking() for _ in range(10)]
        decisions = select_within_budget(rankings, config)
        assert len(decisions) == len(rankings)

    def test_below_threshold_excluded_first(self):
        config = AllocationConfig(hard_rank_threshold=0.5)
        low = make_ranking(aggregate_score=0.2)
        high = make_ranking(aggregate_score=0.8)
        decisions = select_within_budget([low, high], config)
        dec_map = {d.knowledge_item_id: d for d in decisions}
        assert not dec_map[low.knowledge_item_id].selected
        assert dec_map[low.knowledge_item_id].reason == SelectionReason.below_threshold
        assert dec_map[high.knowledge_item_id].selected

    def test_budget_exhaustion_reason(self):
        config = AllocationConfig(
            max_new_cards_per_run=1,
            max_estimated_cost_per_run=1.0,
            hard_rank_threshold=0.0,
        )
        r1 = make_ranking(aggregate_score=0.9, cost=1.0)
        r2 = make_ranking(aggregate_score=0.8, cost=1.0)
        decisions = select_within_budget([r1, r2], config)
        exhausted = [d for d in decisions if d.reason == SelectionReason.budget_exhausted]
        assert len(exhausted) >= 1

    def test_empty_input_returns_empty(self):
        config = AllocationConfig()
        assert select_within_budget([], config) == []

    def test_utility_density_ordering(self):
        """Higher utility density should be selected first."""
        config = AllocationConfig(
            max_new_cards_per_run=1,
            max_estimated_cost_per_run=1.0,
            hard_rank_threshold=0.0,
        )
        low_density = make_ranking(aggregate_score=0.4, cost=1.0, utility_density=0.4)
        high_density = make_ranking(aggregate_score=0.4, cost=1.0, utility_density=0.9)
        decisions = select_within_budget([low_density, high_density], config)
        dec_map = {d.knowledge_item_id: d for d in decisions}
        assert dec_map[high_density.knowledge_item_id].selected
        assert not dec_map[low_density.knowledge_item_id].selected
