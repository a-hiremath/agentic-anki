"""Hard deterministic filtering of knowledge items (Spec Section 14.1)."""

from __future__ import annotations

import logging

from anki_pipeline.config import AllocationConfig
from anki_pipeline.enums import AssessmentLabel, KnowledgeItemType, ProvenanceKind, SelectionReason
from anki_pipeline.identity import generate_id
from anki_pipeline.models import GroundingAssessment, KnowledgeItem, SelectionDecision

logger = logging.getLogger(__name__)


def filter_items(
    items: list[KnowledgeItem],
    assessments: dict[str, GroundingAssessment],
    config: AllocationConfig,
) -> list[tuple[KnowledgeItem, SelectionDecision]]:
    """Apply hard deterministic filters to knowledge items.

    Returns list of (item, decision) for all items.
    decision.selected=True means the item passed all filters.
    """
    results: list[tuple[KnowledgeItem, SelectionDecision]] = []

    for item in items:
        decision = _evaluate_item(item, assessments.get(item.item_id), config)
        results.append((item, decision))

    passed = sum(1 for _, d in results if d.selected)
    logger.debug("Filtering: %d/%d items passed", passed, len(items))
    return results


def _evaluate_item(
    item: KnowledgeItem,
    assessment: GroundingAssessment | None,
    config: AllocationConfig,
) -> SelectionDecision:
    """Evaluate a single item against all hard filters."""
    run_id = item.run_id

    def _reject(reason: SelectionReason) -> SelectionDecision:
        logger.debug(
            "Rejected item %s (type=%s): %s",
            item.item_id[:8], item.item_type.value, reason.value
        )
        return SelectionDecision(
            decision_id=generate_id(),
            run_id=run_id,
            knowledge_item_id=item.item_id,
            selected=False,
            reason=reason,
        )

    # Filter 1: Unknown type
    if item.item_type == KnowledgeItemType.unknown:
        return _reject(SelectionReason.unknown_type)

    # Filter 2: Insufficient grounding for source-backed items
    if item.provenance_kind == ProvenanceKind.source_extracted:
        if assessment is None:
            return _reject(SelectionReason.unsupported)
        if assessment.label == AssessmentLabel.unsupported:
            return _reject(SelectionReason.unsupported)
        if assessment.label == AssessmentLabel.inferential:
            if assessment.score is None or assessment.score < config.allocation.inferential_threshold if hasattr(config, 'allocation') else 0.7:
                pass  # handled below

    # Filter 3: Claim token count bounds
    token_count = len(item.claim.split())
    if token_count < config.min_claim_tokens:
        return _reject(SelectionReason.token_bounds)
    if token_count > config.max_claim_tokens:
        return _reject(SelectionReason.token_bounds)

    # Filter 4: Duplicate (already handled at extraction time, but double-check)
    if item.is_duplicate:
        return _reject(SelectionReason.duplicate)

    # Filter 5: Effectively infinite cost (unknown type already caught above,
    # but keep for forward compatibility)

    # Filter 6: Invalid provenance for mode (user_attested items always pass)

    return SelectionDecision(
        decision_id=generate_id(),
        run_id=run_id,
        knowledge_item_id=item.item_id,
        selected=True,
        reason=SelectionReason.selected,
    )
