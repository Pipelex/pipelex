# Track — CLI Delivery

## What this track is

How errors are rendered to the two CLI audiences: humans through the main `pipelex` CLI (Rich panels) and agents through `pipelex-agent` (structured output). The track also covers the success-path delivery for the agent CLI, because the error path inherits the format option.

Today human Rich delivery and agent JSON delivery work and both consume `to_error_report()`. Two gaps remain: the agent CLI doesn't yet support markdown-default output for `run` / `validate` / `init` (only `models` / `doctor` / `check-model` do), and the Rich handler functions in `error_handlers.py` duplicate the same panel shape across many near-identical functions.

## Current state

### Human CLI — Rich

`pipelex/cli/error_handlers.py` defines per-error-type handler functions, each shaped roughly as:

```python
def handle_<error_type>(exc: <ErrorType>, context: ErrorContext) -> NoReturn:
    report = exc.to_error_report()
    console = get_console()
    console.print(f"\n[bold red]❌ {context} failed because ...[/bold red]\n")
    console.print(f"[bold cyan]<field>:[/bold cyan] [yellow]{escape(exc.<field>)}[/yellow]")
    console.print(f"\n[bold red]Error:[/bold red] {escape(exc.message)}\n")
    tip = report.user_action or "<fallback tip>"
    console.print(f"[bold green]💡 Tip:[/bold green] {escape(tip)}")
    console.print(f"[dim]Learn more: {URLs.documentation}[/dim]")
    console.print(f"[dim]Discord: {URLs.discord}[/dim]\n")
    raise typer.Exit(1) from exc
```

Handlers exist for: `PipeOperatorModelChoiceError`, `PipeOperatorModelAvailabilityError`, `ModelDeckPresetValidatonError`, `ValidateBundleError`, `InferenceSetupRequiredError`, `TelemetryConfigValidationError`, `GatewayTermsNotAcceptedError`, `GatewayApiKeyMissingError`, `GatewayDoNotTrackConflictError`, `RemoteConfigFetchError`, `RemoteConfigValidationError`. The `report.user_action` consumption is the Phase 1 wiring — it landed and works.

`ErrorContext` (a `StrEnum`) describes where the error happened: `PIPE_RUN`, `VALIDATION`, `BUILD`, plus pre-validation contexts.

### Agent CLI — JSON path

`pipelex/cli/agent_cli/commands/agent_output.py` defines:

- `CliOutputFormat` (`StrEnum`): `JSON`, `MARKDOWN`.
- `agent_error(message, error_type, cause, **extra)` — prints structured JSON to stderr and `raise typer.Exit(1) from cause`.
- `agent_success(result)` — prints JSON to stdout.
- `extract_validation_errors(exc: ValidateBundleError)` — flattens blueprint / factory / validation / instantiation errors into a list per-category. This is the most structured error delivery in the codebase and remains the reference shape.

`agent_error()` builds the output JSON as:

```json
{
  "error": true,
  "error_type": "LLMCompletionError",
  "message": "...",
  "hint": "...",
  "retryable": true,
  "error_domain": "runtime",
  "error_category": "transient",
  "model": "gpt-4o",
  "provider": "openai",
  "error_source": ["LLMCompletionError @ .../worker.py:152 (in _gen_text)"]
}
```

It reads `cause.to_error_report()` when `cause` is a `PipelexError` and pulls `user_action`, `retryable`, `error_category`, `model`, `provider` from the report. It falls back to `AGENT_ERROR_HINTS.get(error_type)` for `hint`. `error_domain` is **always** sourced from the dict — see [track-metadata-model.md](track-metadata-model.md).

`_build_error_source(exc)` walks the `__cause__` chain and emits `"ExceptionType @ filename:line (in function)"`, prioritizing frames inside `/pipelex/` over `.venv/` frames.

### Agent CLI — markdown where it exists

The contract documented in `pipelex/cli/agent_cli/CLAUDE.md` is "Default format is markdown for all commands except `inputs`/`concept`/`pipe`/`fmt`/`lint`". Today this is true for `models`, `doctor`, `check-model` — each takes `--format markdown|json` with markdown as default. `run`, `validate`, and `init` do not yet support `--format`; they always go through `agent_success(dict)` (JSON).

There is one markdown-by-default error path already: `InferenceSetupRequiredError` is rendered as a markdown setup-guidance message to stdout with exit 0 (used by agent skills on first run). All other agent errors go through `agent_error()` as JSON to stderr.

### Validation error special case

`ValidateBundleError` (defined in `pipelex/pipeline/validate_bundle.py`) aggregates four error sources:

1. Blueprint validation errors (from interpreter).
2. Pipe factory errors (e.g. missing concepts).
3. Pipe validation errors (e.g. missing inputs, type mismatches).
4. Pipe / concept instantiation errors (pydantic validation during factory).

`extract_validation_errors` returns a flat list of dicts, each with at minimum `category`, `error_type`, and `message`, plus contextual fields per category. The Rich path uses `_display_validation_error_details` in `pipelex/cli/error_handlers.py` to render the same structure as styled blocks.

## Open gaps

### Eleven near-identical Rich handlers

Every handler in `error_handlers.py` follows the same shape: red banner, structured fields, `report.user_action or "<fallback>"` tip, doc/Discord links, `raise typer.Exit(1) from exc`. The fixed fields (the banner / tip / links / raise pattern) are pure boilerplate; only the structured-fields block changes between handlers. Extracting `display_error_panel(console, title, fields, tip, links)` or similar would cut the file roughly in half and put the canonical layout in one place.

### Agent CLI markdown contract is incomplete

`run`, `validate`, and `init` always emit JSON. The `CLAUDE.md` contract states markdown is the default. The error path inherits the format option; today errors are always JSON (except for the one `InferenceSetupRequiredError` markdown special case).

The skills under `../skills/skills/` consume the agent CLI and expect markdown by default for human-readable output. The mismatch between contract and reality is a real friction point for skill maintainers.

## Followups

### 1. Extract a generic Rich panel helper

In `pipelex/cli/error_handlers.py`, introduce a helper such as:

```python
def display_error_panel(
    console: Console,
    *,
    title: str,
    fields: list[tuple[str, str]],          # (label, escaped value)
    error_message: str,
    tip: str,
    links: list[tuple[str, str]],            # (label, url)
) -> None:
    ...
```

Rewrite each `handle_*` to construct the field list and call the helper. The exception-specific logic (`if exc.fallback_list:`, `if exc.enabled_backends:`) stays in the handler, but the panel shape lives in one place. Verify all eleven handlers continue to render identically by snapshot-testing one or two representative outputs.

### 2. Add `agent_error_markdown()` and a format-aware dispatch

Define `agent_error_markdown(message, error_type, cause, **extra)` in `agent_output.py` mirroring `agent_error()` but rendering as markdown to stderr: heading with error type, message body, hint as a tip callout, `error_source` as a code block. Still `raise typer.Exit(1) from cause`.

Introduce a way for commands to pass the current `CliOutputFormat` to the error path. Options:

- Pass `format` explicitly to a new `agent_error_dispatch(format, ...)` wrapper.
- Thread via a context var (`agent_cli_format: ContextVar[CliOutputFormat]`).

Keep `agent_error()` (JSON) as the default when format is unknown — e.g. errors during init before the format is parsed.

### 3. Add `--format markdown|json` to `run`, `validate`, `init`

Match the existing pattern from `models_cmd.py` (`match/case` on `CliOutputFormat`). Default to `MARKDOWN`.

- `run` (pipe / bundle / method): JSON path unchanged (`agent_success(result)`). Markdown path: new `_format_run_markdown(result)` that renders `main_stuff` content (markdown representation if available, else formatted JSON), output file path, graph file path.
- `validate` (pipe / bundle / method): JSON path unchanged. Markdown path: new `_format_validate_markdown(result)` that renders pass/fail summary, list of validated pipes with status, error details if any.
- `init`: Markdown path is a simple confirmation with target dir, backends enabled, routing profile.

Files: `pipelex/cli/agent_cli/commands/run/{pipe_cmd.py, bundle_cmd.py, method_cmd.py}`, `pipelex/cli/agent_cli/commands/validate/{pipe_cmd.py, bundle_cmd.py, method_cmd.py}`, `pipelex/cli/agent_cli/commands/init_cmd.py`.

### 4. Wire format into the agent CLI error handlers

`make_pipelex_for_agent_cli()` (`pipelex/cli/agent_cli/commands/agent_cli_factory.py`) catches init errors before the format option is parsed — keep JSON for these. Command-level error handlers respect the format option.

### 5. Update `pipelex/cli/agent_cli/CLAUDE.md`

Once the markdown defaults are in, refresh the doc:

- Default format is markdown for all commands except `inputs` / `concept` / `pipe` / `fmt` / `lint`.
- `--format json` is available on `run`, `validate`, `init`, `models`, `doctor`, `check-model`.
- Errors respect the same format option.
- Document the markdown structure for each command.

### 6. Tests

- `run` with no `--format` produces markdown to stdout.
- `run --format json` produces valid JSON to stdout.
- `validate` with no `--format` produces markdown.
- Errors produce markdown to stderr by default.
- Errors with `--format json` produce JSON to stderr.
- `inputs` command is unaffected (always JSON).
- After the panel-helper refactor: representative Rich error outputs match a snapshot to confirm no rendering drift.

## Related tracks

- [track-metadata-model.md](track-metadata-model.md) — `to_error_report()` is the canonical data source for both delivery paths; the dict drift it discusses is the metadata that feeds these renderers.
- [track-testing.md](track-testing.md) — full-chain integration snapshot lives there.
