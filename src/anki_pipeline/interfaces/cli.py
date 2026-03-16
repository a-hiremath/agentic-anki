"""Click CLI entry point (Spec Section 19)."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

console = Console()
logger = logging.getLogger(__name__)


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )


def _get_db_and_config(config_path: str | None) -> tuple:
    from anki_pipeline.config import load_config
    from anki_pipeline.storage import Database

    cfg = load_config(Path(config_path) if config_path else None)
    db = Database(Path(cfg.db_path))
    return cfg, db


@click.group()
@click.option("--verbose", "-v", is_flag=True, help="Enable debug logging")
@click.option("--config", "-c", default=None, help="Path to pipeline.yaml config file")
@click.pass_context
def cli(ctx: click.Context, verbose: bool, config: str | None) -> None:
    """Anki Pipeline — generate Anki notes from STEM material."""
    _setup_logging(verbose)
    ctx.ensure_object(dict)
    ctx.obj["config_path"] = config


# ---------------------------------------------------------------------------
# anki-pipeline run
# ---------------------------------------------------------------------------

@cli.command()
@click.option("--source", "-s", required=True, help="Path to source file (PDF, MD, TXT)")
@click.option("--deck", "-d", required=True, help='Anki deck (e.g. "Math::Calc1C")')
@click.option(
    "--mode",
    type=click.Choice(["document", "concept"]),
    default="document",
    help="Pipeline entry mode",
)
@click.pass_context
def run(ctx: click.Context, source: str, deck: str, mode: str) -> None:
    """Run the full pipeline for a source file or concept."""
    from anki_pipeline.config import load_config
    from anki_pipeline.llm.client import LLMClient
    from anki_pipeline.prompt_registry import PromptRegistry
    from anki_pipeline.runs.orchestration import PipelineOrchestrator
    from anki_pipeline.storage import Database

    cfg, db = _get_db_and_config(ctx.obj.get("config_path"))
    llm = LLMClient(model=cfg.model)
    prompts_dir = Path(__file__).parent.parent / "config" / "prompts"
    prompts = PromptRegistry(prompts_dir)
    orchestrator = PipelineOrchestrator(cfg, db, llm, prompts)

    if mode == "document":
        source_path = Path(source)
        if not source_path.exists():
            console.print(f"[red]Source file not found: {source_path}[/red]")
            sys.exit(1)
        console.print(f"[bold]Running document pipeline:[/bold] {source_path} → {deck}")
        pipeline_run = orchestrator.run_document(source_path, deck)
    else:
        # Concept mode: prompt for structured input
        console.print("[bold]Concept mode — enter knowledge item details:[/bold]")
        item_type = click.prompt(
            "Item type",
            type=click.Choice(["definition", "mechanism", "distinction", "formula",
                               "procedure", "exception", "heuristic"]),
        )
        claim = click.prompt("Claim (the atomic fact)")
        subject_tag_root = click.prompt("Subject tag root (e.g. math.calc1c)", default="")
        why_memorable = click.prompt("Why memorable? (optional)", default="")

        concept_input = {
            "item_type": item_type,
            "claim": claim,
            "subject_tag_root": subject_tag_root,
            "why_memorable": why_memorable or None,
        }
        pipeline_run = orchestrator.run_concept(concept_input, deck)

    console.print(f"\n[green]Run completed:[/green] {pipeline_run.run_id}")
    console.print(f"Status: {pipeline_run.status.value}")


# ---------------------------------------------------------------------------
# anki-pipeline review
# ---------------------------------------------------------------------------

@cli.command()
@click.option("--deck", "-d", default=None, help="Filter to a specific deck")
@click.option("--run-id", default=None, help="Filter to a specific run ID")
@click.option("--show-invalid", is_flag=True, help="Also show failed-validation notes")
@click.pass_context
def review(ctx: click.Context, deck: str | None, run_id: str | None, show_invalid: bool) -> None:
    """Interactively review and approve generated note candidates."""
    from anki_pipeline.config import load_config, ReviewConfig
    from anki_pipeline.retrieval_design.review import review_session

    cfg, db = _get_db_and_config(ctx.obj.get("config_path"))
    review_cfg = ReviewConfig(show_invalid=show_invalid)
    actions = review_session(db, run_id=run_id, config=review_cfg, deck=deck)
    console.print(f"\n[green]Review session complete:[/green] {len(actions)} decisions made")


# ---------------------------------------------------------------------------
# anki-pipeline export
# ---------------------------------------------------------------------------

@cli.command()
@click.option("--deck", "-d", required=True, help="Deck to export")
@click.option("--run-id", default=None, help="Run ID for tracking")
@click.option(
    "--method",
    type=click.Choice(["tsv", "direct"]),
    default=None,
    help="Export method (overrides config)",
)
@click.pass_context
def export(ctx: click.Context, deck: str, run_id: str | None, method: str | None) -> None:
    """Export reviewed notes to TSV or directly into Anki."""
    from anki_pipeline.identity import generate_id
    from anki_pipeline.retrieval_design.anki_connect import AnkiConnectClient, AnkiConnectError
    from anki_pipeline.retrieval_design.export import export_deck

    cfg, db = _get_db_and_config(ctx.obj.get("config_path"))
    effective_run_id = run_id or generate_id()
    output_dir = Path(cfg.export.output_dir)
    export_config = cfg.export if method is None else cfg.export.model_copy(update={"method": method})

    if export_config.method == "direct":
        client = AnkiConnectClient(
            url=export_config.anki_connect_url,
            timeout=export_config.anki_connect_timeout,
        )
        try:
            version = client.health_check()
        except AnkiConnectError as exc:
            console.print("[red]Anki is not running or AnkiConnect is not installed.[/red]")
            console.print(f"[red]Error: {exc}[/red]")
            console.print(
                "[yellow]Start Anki, install the AnkiConnect add-on (code 2055492159), then retry.[/yellow]"
            )
            sys.exit(1)
        console.print(f"[dim]AnkiConnect API v{version} detected.[/dim]")

    result = export_deck(db, deck, effective_run_id, output_dir, config=export_config)
    if export_config.method == "direct":
        console.print(
            f"\n[green]Direct export complete:[/green] {result.n_added} added, {result.n_failed} failed"
        )
    else:
        console.print(f"\n[green]Export complete:[/green] {len(result.records)} notes exported")

    if result.records:
        console.print(f"Output: {result.records[0].output_file}")


# ---------------------------------------------------------------------------
# anki-pipeline status
# ---------------------------------------------------------------------------

@cli.command()
@click.option("--source", "-s", default=None, help="Filter by source file path")
@click.option("--deck", "-d", default=None, help="Filter by deck")
@click.option("--run-id", default=None, help="Show status of a specific run")
@click.pass_context
def status(ctx: click.Context, source: str | None, deck: str | None, run_id: str | None) -> None:
    """Show pipeline status and counts."""
    cfg, db = _get_db_and_config(ctx.obj.get("config_path"))

    with db.connect() as conn:
        # Runs
        if run_id:
            row = conn.execute(
                "SELECT * FROM pipeline_runs WHERE run_id = ?", (run_id,)
            ).fetchone()
            if row:
                console.print(f"[bold]Run {run_id}[/bold]")
                console.print(f"  Status: {row['status']}")
                console.print(f"  Mode: {row['entry_mode']}")
                console.print(f"  Deck: {row['deck_target']}")
                console.print(f"  Started: {row['started_at']}")
                console.print(f"  Finished: {row['finished_at']}")
            else:
                console.print(f"[red]Run not found: {run_id}[/red]")
            return

        # Summary counts
        table = Table(title="Pipeline Status")
        table.add_column("Metric")
        table.add_column("Count", justify="right")

        counts = {
            "Total runs": conn.execute("SELECT COUNT(*) FROM pipeline_runs").fetchone()[0],
            "Sources ingested": conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0],
            "Chunks": conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0],
            "Knowledge items (active)": conn.execute(
                "SELECT COUNT(*) FROM knowledge_items WHERE is_active=1"
            ).fetchone()[0],
            "Note candidates": conn.execute("SELECT COUNT(*) FROM note_candidates").fetchone()[0],
            "Passed validation": conn.execute(
                "SELECT COUNT(*) FROM validation_results WHERE passed=1"
            ).fetchone()[0],
            "Reviewed notes": conn.execute("SELECT COUNT(*) FROM reviewed_notes").fetchone()[0],
            "Exported": conn.execute(
                "SELECT COUNT(*) FROM export_records WHERE status='success'"
            ).fetchone()[0],
        }

        for metric, count in counts.items():
            table.add_row(metric, str(count))

        console.print(table)


# ---------------------------------------------------------------------------
# anki-pipeline rerun
# ---------------------------------------------------------------------------

@cli.command()
@click.option("--source", "-s", required=True, help="Source file path")
@click.option("--stage", required=True, help="Stage to restart from (e.g. synthesis)")
@click.option("--deck", "-d", required=True, help="Anki deck")
@click.pass_context
def rerun(ctx: click.Context, source: str, stage: str, deck: str) -> None:
    """Rerun the pipeline from a specific stage, preserving prior artifacts."""
    from anki_pipeline.enums import RunStage
    from anki_pipeline.llm.client import LLMClient
    from anki_pipeline.prompt_registry import PromptRegistry
    from anki_pipeline.runs.orchestration import PipelineOrchestrator

    try:
        run_stage = RunStage(stage)
    except ValueError:
        valid = [s.value for s in RunStage]
        console.print(f"[red]Invalid stage: {stage!r}. Valid stages: {valid}[/red]")
        sys.exit(1)

    cfg, db = _get_db_and_config(ctx.obj.get("config_path"))
    llm = LLMClient(model=cfg.model)
    prompts_dir = Path(__file__).parent.parent / "config" / "prompts"
    prompts = PromptRegistry(prompts_dir)
    orchestrator = PipelineOrchestrator(cfg, db, llm, prompts)

    source_path = Path(source)
    pipeline_run = orchestrator.rerun(source_path, run_stage, deck)
    console.print(f"\n[green]Rerun completed:[/green] {pipeline_run.run_id}")
