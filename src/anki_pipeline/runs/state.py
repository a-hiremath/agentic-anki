"""Run state tracking."""

from __future__ import annotations

import datetime
import logging
from dataclasses import dataclass, field

from anki_pipeline.enums import RunStage, RunStatus

logger = logging.getLogger(__name__)


@dataclass
class RunState:
    """Tracks state of a pipeline run in progress."""
    run_id: str
    started_at: datetime.datetime = field(default_factory=datetime.datetime.utcnow)
    current_stage: RunStage | None = None
    stages_completed: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    status: RunStatus = RunStatus.running

    def begin_stage(self, stage: RunStage) -> None:
        self.current_stage = stage
        logger.info("run=%s stage=%s status=started", self.run_id, stage.value)

    def complete_stage(self, stage: RunStage) -> None:
        self.stages_completed.append(stage.value)
        self.current_stage = None
        logger.info("run=%s stage=%s status=completed", self.run_id, stage.value)

    def record_error(self, message: str) -> None:
        self.errors.append(message)
        logger.error("run=%s error=%r", self.run_id, message)

    def mark_completed(self) -> None:
        self.status = RunStatus.completed

    def mark_failed(self, message: str) -> None:
        self.status = RunStatus.failed
        self.record_error(message)
