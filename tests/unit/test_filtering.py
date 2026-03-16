"""Tests for allocation filtering (Spec Section 14.1)."""

import pytest

from anki_pipeline.allocation.filtering import filter_items
from anki_pipeline.config import AllocationConfig
from anki_pipeline.enums import AssessmentLabel, KnowledgeItemType, ProvenanceKind, SelectionReason
from anki_pipeline.identity import generate_id
from anki_pipeline.models import GroundingAssessment, KnowledgeItem


def make_item(
    item_type=KnowledgeItemType.definition,
    claim="A set is a collection of distinct elements.",
    provenance=ProvenanceKind.source_extracted,
    is_duplicate=False,
) -> KnowledgeItem:
    return KnowledgeItem(
        item_id=generate_id(),
        run_id="run1",
        item_type=item_type,
        claim=claim,
        content_hash=generate_id(),
        deck_target="Math",
        provenance_kind=provenance,
        is_duplicate=is_duplicate,
    )


def make_assessment(item_id: str, label=AssessmentLabel.direct, score=0.9) -> GroundingAssessment:
    return GroundingAssessment(
        assessment_id=generate_id(),
        run_id="run1",
        knowledge_item_id=item_id,
        label=label,
        score=score,
    )


def default_config() -> AllocationConfig:
    return AllocationConfig()


class TestFilterItems:
    def test_unknown_type_rejected(self):
        item = make_item(item_type=KnowledgeItemType.unknown)
        results = filter_items([item], {}, default_config())
        assert len(results) == 1
        _, decision = results[0]
        assert not decision.selected
        assert decision.reason == SelectionReason.unknown_type

    def test_unsupported_item_rejected(self):
        item = make_item()
        assessment = make_assessment(item.item_id, label=AssessmentLabel.unsupported, score=0.0)
        results = filter_items([item], {item.item_id: assessment}, default_config())
        _, decision = results[0]
        assert not decision.selected
        assert decision.reason == SelectionReason.unsupported

    def test_no_assessment_rejects_source_item(self):
        item = make_item()
        results = filter_items([item], {}, default_config())
        _, decision = results[0]
        assert not decision.selected
        assert decision.reason == SelectionReason.unsupported

    def test_user_attested_passes_without_assessment(self):
        item = make_item(provenance=ProvenanceKind.user_attested)
        results = filter_items([item], {}, default_config())
        _, decision = results[0]
        assert decision.selected

    def test_token_bounds_short_claim_rejected(self):
        item = make_item(claim="too short")  # < 5 tokens? "too short" = 2 tokens
        item2 = make_item(claim="a b")  # 2 tokens
        assessment = make_assessment(item2.item_id)
        results = filter_items([item2], {item2.item_id: assessment}, default_config())
        _, decision = results[0]
        assert not decision.selected
        assert decision.reason == SelectionReason.token_bounds

    def test_duplicate_rejected(self):
        item = make_item(is_duplicate=True)
        assessment = make_assessment(item.item_id)
        results = filter_items([item], {item.item_id: assessment}, default_config())
        _, decision = results[0]
        assert not decision.selected
        assert decision.reason == SelectionReason.duplicate

    def test_valid_item_passes(self):
        item = make_item(
            claim="The derivative of x squared is two x by the power rule."
        )
        assessment = make_assessment(item.item_id, label=AssessmentLabel.direct, score=0.95)
        results = filter_items([item], {item.item_id: assessment}, default_config())
        _, decision = results[0]
        assert decision.selected

    def test_every_item_gets_decision(self):
        items = [make_item() for _ in range(5)]
        assessments = {i.item_id: make_assessment(i.item_id) for i in items}
        results = filter_items(items, assessments, default_config())
        assert len(results) == len(items)

    def test_all_rejections_have_reason(self):
        items = [
            make_item(item_type=KnowledgeItemType.unknown),
            make_item(claim="too"),  # 1 token
        ]
        results = filter_items(items, {}, default_config())
        for _, decision in results:
            assert not decision.selected
            assert decision.reason is not None
