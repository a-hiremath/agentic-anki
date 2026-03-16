# agentic-anki
Automated Anki flashcard pipeline for turning STEM source material into reviewed, exportable notes.

## What this does
`agentic-anki` runs a staged pipeline:
1. Ingest source text (`.pdf`, `.md`, `.txt`, `.tex`)
2. Chunk content
3. Extract knowledge items
4. Ground and rank items
5. Synthesize note candidates
6. Validate candidates
7. Human review
8. Export as TSV or directly to Anki via AnkiConnect

All artifacts are stored in a local SQLite DB (`pipeline.db` by default).

## Requirements
- Python `>=3.12`
- Anthropic API key in environment (`ANTHROPIC_API_KEY`)
- For direct export only:
  - Anki Desktop running locally
  - AnkiConnect add-on installed (code `2055492159`)

## Installation
From the repo root:

```powershell
python -m venv .venv
.\.venv\Scripts\activate
python -m pip install -U pip
pip install -e .
```

Set API key in current PowerShell session:

```powershell
$env:ANTHROPIC_API_KEY="your_api_key_here"
```

For persistent Windows setup:

```powershell
setx ANTHROPIC_API_KEY "your_api_key_here"
```

Then open a new terminal.

## Configuration
Default config file: `src/anki_pipeline/config/pipeline.yaml`

Key fields:
- `db_path`: SQLite path
- `model`: default LLM model
- `chunking`, `extraction`, `grounding`, `allocation`, `validation`, `ranking`: stage configs
- `export.output_dir`: export folder
- `export.method`: `tsv` or `direct`
- `export.anki_connect_url`: direct export endpoint (default `http://localhost:8765`)
- `export.anki_connect_timeout`: direct export timeout in seconds

You can pass a custom config file to any command:

```powershell
anki-pipeline --config .\my_pipeline.yaml <command> ...
```

## Quickstart: First cards end to end
Use a sample file first to validate your setup:

```powershell
anki-pipeline run --source .\tests\fixtures\sample_math.md --deck "Math::Calc1C"
```

Review candidates:

```powershell
anki-pipeline review --deck "Math::Calc1C"
```

Export (TSV mode):

```powershell
anki-pipeline export --deck "Math::Calc1C" --method tsv
```

Or direct export to Anki:

```powershell
anki-pipeline export --deck "Math::Calc1C" --method direct
```

Check status:

```powershell
anki-pipeline status
```

## CLI commands
### `run`
Run pipeline from a document or concept input.

```powershell
anki-pipeline run --source .\path\to\file.pdf --deck "Physics::Mechanics"
```

Concept mode (interactive prompts):

```powershell
anki-pipeline run --mode concept --source ignored --deck "CS::Algorithms"
```

Note: `--source` is required by the CLI even when `--mode concept`; it is only used in document mode.

### `review`
Interactive terminal review over pending validated note candidates.

```powershell
anki-pipeline review --deck "Physics::Mechanics"
anki-pipeline review --run-id <run_id>
anki-pipeline review --show-invalid
```

Actions in review prompt:
- `a` accept
- `r` reject
- `e` edit in `$EDITOR` (or `notepad` on Windows if unset)
- `s` skip
- `q` quit

### `export`
Export reviewed notes for a deck.

```powershell
anki-pipeline export --deck "Physics::Mechanics"
anki-pipeline export --deck "Physics::Mechanics" --method tsv
anki-pipeline export --deck "Physics::Mechanics" --method direct
```

Behavior:
- `tsv`: appends rows into `output/<deck>.tsv`
- `direct`: sends notes through AnkiConnect and also writes an audit TSV in output dir
- `--method` overrides config for that run

### `status`
Inspect aggregate counts or a specific run.

```powershell
anki-pipeline status
anki-pipeline status --run-id <run_id>
```

### `rerun`
Rerun a source from a specific stage.

```powershell
anki-pipeline rerun --source .\path\to\file.md --stage synthesis --deck "Math::Calc1C"
```

## Export modes
### TSV mode
Use when you want manual import in Anki:
1. Run `anki-pipeline export --method tsv`
2. In Anki, import generated TSV from `output/`
3. Map fields to your note type as needed

### Direct mode (AnkiConnect)
Use when Anki Desktop is running and AnkiConnect is installed:
1. Start Anki Desktop
2. Ensure AnkiConnect add-on is installed (`2055492159`)
3. Run direct export:

```powershell
anki-pipeline export --deck "Math::Calc1C" --method direct
```

If reachable, CLI prints detected AnkiConnect API version before export.

## Typical workflow for real documents
1. `run` on one source with a single deck target
2. `review` and reject/edit aggressively for quality
3. `export` to TSV or direct
4. `status` to confirm counts
5. Iterate with more sources

## Testing
Run full test suite:

```powershell
python -m pytest -q
```

## Troubleshooting
### `ANTHROPIC_API_KEY` missing or invalid
- Symptom: extraction/ranking/synthesis stages fail
- Fix: set valid key in environment and open a new shell

### Direct export says Anki is not running
- Start Anki Desktop
- Install AnkiConnect add-on (`2055492159`)
- Verify URL/timeout in config:

```yaml
export:
  method: direct
  anki_connect_url: http://localhost:8765
  anki_connect_timeout: 10
```

### No notes appear during review/export
- Check `anki-pipeline status`
- Common reasons:
  - candidates failed validation
  - everything was already reviewed/exported for that method
  - deck filter doesn’t match deck target used in `run`

### Source file not found
- Pass an existing absolute or relative path to `--source`

## Notes on idempotency
- Exports are tracked by method (`tsv` vs `direct`)
- A successful TSV export does not block direct export of the same reviewed note
- Failed direct exports are recorded as failed and can be retried later
