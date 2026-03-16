"""LLM-assisted importance/forgettability/testability scoring (Spec Section 14.2)."""

from __future__ import annotations

import json
import logging

from anki_pipeline.config import RankingConfig
from anki_pipeline.identity import generate_id
from anki_pipeline.llm.client import LLMClient
from anki_pipeline.llm.schemas import RankingResponse
from anki_pipeline.models import KnowledgeItem, RankingAssessment
from anki_pipeline.prompt_registry import PromptRegistry

logger = logging.getLogger(__name__)


def score_items(
    items: list[KnowledgeItem],
    run_id: str,
    llm: LLMClient,
    prompts: PromptRegistry,
    config: RankingConfig,
    deck_target: str = "",
) -> list[RankingAssessment]:
    """Score items via LLM on importance, forgettability, testability.

    Returns a RankingAssessment for each item.
    """
    if not items:
        return []

    template = prompts.get("ranking")
    system = "You are a spaced-repetition curriculum designer scoring knowledge items."

    items_json = json.dumps(
        [
            {
                "item_id": item.item_id,
                "item_type": item.item_type.value,
                "claim": item.claim,
            }
            for item in items
        ],
        indent=2,
    )

    user = template.render(
        deck_target=deck_target,
        subject_tag_root=items[0].subject_tag_root if items else "",
        items_json=items_json,
    )

    try:
        response: RankingResponse = llm.structured_call(
            output_schema=RankingResponse,
            system=system,
            user=user,
            max_tokens=config.max_tokens,
        )
        ranked_map = {r.item_id: r for r in response.rankings}
    except Exception as exc:
        logger.error("Scoring failed: %s. Using default scores.", exc)
        ranked_map = {}

    assessments: list[RankingAssessment] = []
    for item in items:
        ranked = ranked_map.get(item.item_id)
        if ranked:
            importance = max(0.0, min(1.0, ranked.importance))
            forgettability = max(0.0, min(1.0, ranked.forgettability))
            testability = max(0.0, min(1.0, ranked.testability))
        else:
            importance = forgettability = testability = 0.5  # default

        aggregate = (
            config.weight_importance * importance
            + config.weight_forgettability * forgettability
            + config.weight_testability * testability
        )

        cost = config.estimated_card_cost.get(item.item_type.value, 1.0)
        utility = aggregate / cost if cost > 0 else 0.0

        assessments.append(
            RankingAssessment(
                ranking_id=generate_id(),
                run_id=run_id,
                knowledge_item_id=item.item_id,
                importance=importance,
                forgettability=forgettability,
                testability=testability,
                aggregate_score=aggregate,
                estimated_card_cost=cost,
                utility_density=utility,
                prompt_version=template.version_hash,
                model_name=llm.model,
            )
        )

    return assessments
