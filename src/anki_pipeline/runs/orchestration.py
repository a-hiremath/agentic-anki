"""Pipeline runner and phase sequencer (Spec Section 20)."""

from __future__ import annotations

import collections
import datetime
import logging
from pathlib import Path
from typing import Any

from anki_pipeline.config import PipelineConfig
from anki_pipeline.enums import EntryMode, RunStage, RunStatus
from anki_pipeline.identity import generate_id
from anki_pipeline.llm.client import LLMClient
from anki_pipeline.models import KnowledgeItem, PipelineRun
from anki_pipeline.prompt_registry import PromptRegistry
from anki_pipeline.runs.state import RunState
from anki_pipeline.storage import Database, RunRepo

logger = logging.getLogger(__name__)


class PipelineOrchestrator:
    """Orchestrates the full pipeline from source ingestion to export-ready notes.

    Each run creates a new PipelineRun record. Stages are executed sequentially.
    Artifacts from previous stages are preserved on partial failure.
    """

    def __init__(
        self,
        config: PipelineConfig,
        db: Database,
        llm: LLMClient,
        prompts: PromptRegistry,
        grounding_llm: LLMClient | None = None,
    ) -> None:
        self.config = config
        self.db = db
        self.llm = llm
        self.prompts = prompts
        self.grounding_llm = grounding_llm or llm

    # ------------------------------------------------------------------
    # Public entry points
    # ------------------------------------------------------------------

    def run_document(self, source_path: Path, deck_target: str) -> PipelineRun:
        """Run the full pipeline for a document source."""
        run = self._create_run(EntryMode.document, deck_target)
        state = RunState(run_id=run.run_id)
        try:
            run = self._execute_document_pipeline(run, state, source_path, deck_target)
        except Exception as exc:
            state.mark_failed(str(exc))
            self._finalize_run(run, state)
            raise
        else:
            state.mark_completed()
            self._finalize_run(run, state)
        return run

    def run_concept(self, concept_input: dict[str, Any], deck_target: str) -> PipelineRun:
        """Run the pipeline for a user-attested concept (no ingestion/chunking)."""
        run = self._create_run(EntryMode.concept, deck_target)
        state = RunState(run_id=run.run_id)
        try:
            run = self._execute_concept_pipeline(run, state, concept_input, deck_target)
        except Exception as exc:
            state.mark_failed(str(exc))
            self._finalize_run(run, state)
            raise
        else:
            state.mark_completed()
            self._finalize_run(run, state)
        return run

    def rerun(self, source_path: Path, stage: RunStage, deck_target: str) -> PipelineRun:
        """Create a new run starting at the given stage, reusing prior canonical artifacts."""
        run = self._create_run(EntryMode.document, deck_target, trigger="rerun")
        state = RunState(run_id=run.run_id)
        try:
            run = self._execute_rerun_pipeline(run, state, source_path, stage, deck_target)
        except Exception as exc:
            state.mark_failed(str(exc))
            self._finalize_run(run, state)
            raise
        else:
            state.mark_completed()
            self._finalize_run(run, state)
        return run

    # ------------------------------------------------------------------
    # Internal pipeline executors
    # ------------------------------------------------------------------

    def _execute_document_pipeline(
        self, run: PipelineRun, state: RunState, source_path: Path, deck_target: str
    ) -> PipelineRun:
        from anki_pipeline.distillation.ingestion import ingest_source
        from anki_pipeline.distillation.chunking import chunk_source
        from anki_pipeline.distillation.extraction import extract_from_chunk
        from anki_pipeline.distillation.grounding import assess_grounding_batch
        from anki_pipeline.allocation.filtering import filter_items
        from anki_pipeline.allocation.scoring import score_items
        from anki_pipeline.allocation.selection import select_within_budget
        from anki_pipeline.retrieval_design.synthesis import synthesize_notes
        from anki_pipeline.retrieval_design.validation import validate_note
        from anki_pipeline.storage import (
            ChunkRepo, ExtractionAttemptRepo, GroundingAssessmentRepo,
            KnowledgeItemRepo, NoteCandidateRepo, RankingAssessmentRepo,
            SelectionDecisionRepo, SynthesisAttemptRepo, ValidationResultRepo,
        )

        # Stage: Ingestion
        state.begin_stage(RunStage.ingestion)
        with self.db.connect() as conn:
            source = ingest_source(source_path, run_id=run.run_id)
            from anki_pipeline.storage import SourceRepo
            existing = SourceRepo.get_by_fingerprint(conn, source.source_fingerprint)
            if existing:
                source = existing
                logger.info("run=%s Reusing existing source source_id=%s", run.run_id, source.source_id)
            else:
                SourceRepo.insert(conn, source)
        state.complete_stage(RunStage.ingestion)

        # Stage: Chunking
        state.begin_stage(RunStage.chunking)
        with self.db.connect() as conn:
            chunks = chunk_source(source, self.config.chunking)
            for c in chunks:
                c.run_id = run.run_id
            ChunkRepo.insert_batch(conn, chunks)
        state.complete_stage(RunStage.chunking)

        # Stage: Extraction
        state.begin_stage(RunStage.extraction)
        all_items: list[KnowledgeItem] = []
        with self.db.connect() as conn:
            for chunk in chunks:
                items, attempt = extract_from_chunk(
                    chunk, source, self.llm, self.prompts, self.config.extraction,
                    run_id=run.run_id, deck_target=deck_target
                )
                ExtractionAttemptRepo.insert(conn, attempt)
                for item in items:
                    existing_item = KnowledgeItemRepo.get_by_content_hash_and_deck(
                        conn, item.content_hash, deck_target
                    )
                    if existing_item:
                        item.is_duplicate = True
                        attempt.items_duplicate += 1
                    else:
                        KnowledgeItemRepo.insert(conn, item)
                        all_items.append(item)
        state.complete_stage(RunStage.extraction)

        # Stage: Grounding (batched by chunk)
        state.begin_stage(RunStage.grounding)
        assessments: dict[str, Any] = {}
        with self.db.connect() as conn:
            chunk_map = {c.chunk_id: c for c in chunks}
            # Group items by chunk_id for batch processing
            items_by_chunk: dict[str, list[KnowledgeItem]] = collections.defaultdict(list)
            for item in all_items:
                if item.chunk_id and item.chunk_id in chunk_map:
                    items_by_chunk[item.chunk_id].append(item)

            for chunk_id, chunk_items in items_by_chunk.items():
                batch_assessments = assess_grounding_batch(
                    chunk_items, chunk_map[chunk_id],
                    self.grounding_llm, self.prompts,
                    run_id=run.run_id,
                    max_tokens=self.config.grounding.max_tokens,
                )
                for assessment in batch_assessments:
                    GroundingAssessmentRepo.insert(conn, assessment)
                    assessments[assessment.knowledge_item_id] = assessment
        state.complete_stage(RunStage.grounding)

        # Stage: Filtering
        state.begin_stage(RunStage.filtering)
        filter_results = filter_items(all_items, assessments, self.config.allocation)
        grounded_items = [item for item, decision in filter_results if decision.selected]
        with self.db.connect() as conn:
            for _, decision in filter_results:
                SelectionDecisionRepo.insert(conn, decision)
        state.complete_stage(RunStage.filtering)

        # Stage: Scoring
        state.begin_stage(RunStage.scoring)
        rankings = score_items(
            grounded_items, run.run_id, self.llm, self.prompts,
            self.config.ranking, deck_target
        )
        with self.db.connect() as conn:
            for ranking in rankings:
                RankingAssessmentRepo.insert(conn, ranking)
        state.complete_stage(RunStage.scoring)

        # Stage: Selection
        state.begin_stage(RunStage.selection)
        selection_results = select_within_budget(rankings, self.config.allocation)
        selected_item_ids = {d.knowledge_item_id for d in selection_results if d.selected}
        with self.db.connect() as conn:
            for decision in selection_results:
                SelectionDecisionRepo.insert(conn, decision)
        selected_items = [i for i in grounded_items if i.item_id in selected_item_ids]
        state.complete_stage(RunStage.selection)

        # Stage: Synthesis
        state.begin_stage(RunStage.synthesis)
        all_candidates = []
        with self.db.connect() as conn:
            for item in selected_items:
                evidence = assessments.get(item.item_id, None)
                spans = evidence.evidence_spans if evidence else []
                candidates, attempt = synthesize_notes(
                    item, spans, self.llm, self.prompts, run_id=run.run_id
                )
                SynthesisAttemptRepo.insert(conn, attempt)
                for candidate in candidates:
                    NoteCandidateRepo.insert(conn, candidate)
                    all_candidates.extend(candidates)
        state.complete_stage(RunStage.synthesis)

        # Stage: Validation
        state.begin_stage(RunStage.validation)
        with self.db.connect() as conn:
            for candidate in all_candidates:
                result = validate_note(candidate, self.config.validation)
                ValidationResultRepo.insert(conn, result)
        state.complete_stage(RunStage.validation)

        return run

    def _execute_concept_pipeline(
        self, run: PipelineRun, state: RunState, concept_input: dict[str, Any], deck_target: str
    ) -> PipelineRun:
        from anki_pipeline.enums import KnowledgeItemType, ProvenanceKind
        from anki_pipeline.identity import content_hash, generate_id
        from anki_pipeline.allocation.filtering import filter_items
        from anki_pipeline.allocation.scoring import score_items
        from anki_pipeline.allocation.selection import select_within_budget
        from anki_pipeline.retrieval_design.synthesis import synthesize_notes
        from anki_pipeline.retrieval_design.validation import validate_note
        from anki_pipeline.storage import (
            KnowledgeItemRepo, NoteCandidateRepo, RankingAssessmentRepo,
            SelectionDecisionRepo, SynthesisAttemptRepo, ValidationResultRepo,
        )

        # Build KnowledgeItem from structured input
        item_type = KnowledgeItemType(concept_input["item_type"])
        claim = concept_input["claim"]
        ch = content_hash(item_type.value, claim)

        item = KnowledgeItem(
            item_id=generate_id(),
            run_id=run.run_id,
            source_id=None,
            chunk_id=None,
            item_type=item_type,
            claim=claim,
            content_hash=ch,
            deck_target=deck_target,
            provenance_kind=ProvenanceKind.user_attested,
            subject_tag_root=concept_input.get("subject_tag_root", ""),
            why_memorable=concept_input.get("why_memorable"),
        )

        with self.db.connect() as conn:
            existing = KnowledgeItemRepo.get_by_content_hash_and_deck(conn, ch, deck_target)
            if existing:
                item.is_duplicate = True
                logger.info("Concept is duplicate, skipping: %s", claim[:60])
                return run
            KnowledgeItemRepo.insert(conn, item)

        # Skip filtering for concepts (user-attested passes automatically)
        # Light ranking
        rankings = score_items(
            [item], run.run_id, self.llm, self.prompts,
            self.config.ranking, deck_target
        )
        with self.db.connect() as conn:
            for ranking in rankings:
                RankingAssessmentRepo.insert(conn, ranking)

        # Selection
        selection_results = select_within_budget(rankings, self.config.allocation)
        with self.db.connect() as conn:
            for decision in selection_results:
                SelectionDecisionRepo.insert(conn, decision)

        selected = [d for d in selection_results if d.selected]
        if not selected:
            logger.info("Concept not selected within budget: %s", claim[:60])
            return run

        # Synthesis
        candidates, attempt = synthesize_notes(
            item, [], self.llm, self.prompts, run_id=run.run_id
        )
        with self.db.connect() as conn:
            SynthesisAttemptRepo.insert(conn, attempt)
            for candidate in candidates:
                NoteCandidateRepo.insert(conn, candidate)

        # Validation
        with self.db.connect() as conn:
            for candidate in candidates:
                result = validate_note(candidate, self.config.validation)
                ValidationResultRepo.insert(conn, result)

        return run

    def _execute_rerun_pipeline(
        self,
        run: PipelineRun,
        state: RunState,
        source_path: Path,
        stage: RunStage,
        deck_target: str,
    ) -> PipelineRun:
        """Rerun from a specific stage, reusing prior source/chunk artifacts."""
        # For simplicity, rerun synthesis onwards from existing selected items
        from anki_pipeline.retrieval_design.synthesis import synthesize_notes
        from anki_pipeline.retrieval_design.validation import validate_note
        from anki_pipeline.storage import (
            GroundingAssessmentRepo, KnowledgeItemRepo, NoteCandidateRepo,
            SelectionDecisionRepo, SynthesisAttemptRepo, ValidationResultRepo,
        )
        from anki_pipeline.identity import source_fingerprint as compute_fp
        from anki_pipeline.normalize import normalize_for_source_hash

        if stage not in (RunStage.synthesis, RunStage.validation):
            # For a full rerun of earlier stages, just run the full pipeline
            return self._execute_document_pipeline(run, state, source_path, deck_target)

        # Find prior source
        text = source_path.read_text(encoding="utf-8")
        fp = compute_fp(text)
        with self.db.connect() as conn:
            from anki_pipeline.storage import SourceRepo
            existing_source = SourceRepo.get_by_fingerprint(conn, fp)
            if not existing_source:
                raise ValueError(f"No prior source found for {source_path}. Run full pipeline first.")

            # Get selected items from prior runs
            rows = conn.execute(
                """
                SELECT ki.* FROM knowledge_items ki
                JOIN selection_decisions sd ON sd.knowledge_item_id = ki.item_id
                WHERE ki.source_id = ? AND sd.selected = 1
                """,
                (existing_source.source_id,),
            ).fetchall()

        items = [KnowledgeItemRepo._row_to_model(r) for r in rows]

        with self.db.connect() as conn:
            for item in items:
                assessment = GroundingAssessmentRepo.get_by_item(conn, item.item_id)
                spans = assessment.evidence_spans if assessment else []
                candidates, attempt = synthesize_notes(
                    item, spans, self.llm, self.prompts, run_id=run.run_id
                )
                SynthesisAttemptRepo.insert(conn, attempt)
                for candidate in candidates:
                    NoteCandidateRepo.insert(conn, candidate)
                    result = validate_note(candidate, self.config.validation)
                    ValidationResultRepo.insert(conn, result)

        return run

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _create_run(
        self, entry_mode: EntryMode, deck_target: str, trigger: str = "manual"
    ) -> PipelineRun:
        run = PipelineRun(
            run_id=generate_id(),
            entry_mode=entry_mode,
            deck_target=deck_target,
            trigger=trigger,
            config_version=self.config.config_hash(),
        )
        with self.db.connect() as conn:
            RunRepo.insert(conn, run)
        logger.info("Created run run_id=%s mode=%s deck=%s", run.run_id, entry_mode.value, deck_target)
        return run

    def _finalize_run(self, run: PipelineRun, state: RunState) -> None:
        finished_at = datetime.datetime.utcnow().isoformat()
        error_message = "; ".join(state.errors) if state.errors else None
        with self.db.connect() as conn:
            RunRepo.update_status(
                conn,
                run.run_id,
                status=state.status.value,
                finished_at=finished_at,
                error_message=error_message,
                stages_completed=state.stages_completed,
            )
        # Update in-memory object too
        run.status = state.status
        run.stages_completed = list(state.stages_completed)
        if error_message:
            run.error_message = error_message
        logger.info(
            "Finalized run run_id=%s status=%s stages=%s",
            run.run_id, state.status.value, state.stages_completed
        )
