"""Budget-constrained selection of knowledge items (Spec Section 14.3)."""

from __future__ import annotations

import logging

from anki_pipeline.config import AllocationConfig
from anki_pipeline.enums import SelectionReason
from anki_pipeline.identity import generate_id
from anki_pipeline.models import RankingAssessment, SelectionDecision

logger = logging.getLogger(__name__)


def select_within_budget(
    rankings: list[RankingAssessment],
    config: AllocationConfig,
) -> list[SelectionDecision]:
    """Greedily select items by utility_density within budget constraints.

    All candidates receive a SelectionDecision (selected or not).

    Algorithm (Spec Section 14.3):
    1. Discard below hard_rank_threshold
    2. Sort by utility_density descending
    3. Greedily admit while within budget
    4. Record all decisions
    """
    if not rankings:
        return []

    run_id = rankings[0].run_id

    # Step 1: Separate below-threshold
    above = [r for r in rankings if r.aggregate_score >= config.hard_rank_threshold]
    below = [r for r in rankings if r.aggregate_score < config.hard_rank_threshold]

    # Step 2: Sort above-threshold by utility_density descending
    above.sort(key=lambda r: r.utility_density, reverse=True)

    # Step 3: Greedy selection
    total_cost = 0.0
    total_cards = 0
    decisions: list[SelectionDecision] = []

    for ranking in above:
        budget_snap = {
            "total_cost": total_cost,
            "total_cards": total_cards,
            "max_cost": config.max_estimated_cost_per_run,
            "max_cards": config.max_new_cards_per_run,
        }

        can_add = (
            total_cost + ranking.estimated_card_cost <= config.max_estimated_cost_per_run
            and total_cards < config.max_new_cards_per_run
        )

        if can_add:
            total_cost += ranking.estimated_card_cost
            total_cards += 1
            decisions.append(
                SelectionDecision(
                    decision_id=generate_id(),
                    run_id=run_id,
                    knowledge_item_id=ranking.knowledge_item_id,
                    selected=True,
                    reason=SelectionReason.selected,
                    budget_snapshot=budget_snap,
                )
            )
        else:
            decisions.append(
                SelectionDecision(
                    decision_id=generate_id(),
                    run_id=run_id,
                    knowledge_item_id=ranking.knowledge_item_id,
                    selected=False,
                    reason=SelectionReason.budget_exhausted,
                    budget_snapshot=budget_snap,
                )
            )

    # Below-threshold decisions
    for ranking in below:
        decisions.append(
            SelectionDecision(
                decision_id=generate_id(),
                run_id=run_id,
                knowledge_item_id=ranking.knowledge_item_id,
                selected=False,
                reason=SelectionReason.below_threshold,
                budget_snapshot={},
            )
        )

    selected = sum(1 for d in decisions if d.selected)
    logger.info(
        "Selection: %d/%d items selected (cost=%.1f, cards=%d)",
        selected, len(rankings), total_cost, total_cards
    )
    return decisions
