# Track — CLI Delivery

## What this track is

How errors are rendered to the two CLI audiences: humans through the main `pipelex` CLI (Rich panels) and agents through `pipelex-agent` (structured output, JSON or markdown). The track also covers the success-path delivery for the agent CLI, because the error path inherits the format option.

Both delivery paths are landed. Human Rich delivery and agent JSON/markdown delivery both consume `to_error_report()`, the agent CLI defaults to markdown with `--format json` available, and the Rich handlers share one panel helper.

## Current state

### Human CLI — Rich

`pipelex/cli/error_handlers.py` defines per-error-type handler functions, each building its panel through the shared `display_error_panel(console, *, title, fields, error_message, tip, links)` helper:

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

Each `handle_*` function constructs the field list and calls the helper; the exception-specific logic (`if exc.fallback_list:`, `if exc.enabled_backends:`) stays in the handler, but the panel shape — red banner, structured fields, `report.user_action` tip, doc/Discord links, `raise typer.Exit(1) from exc` — lives in one place. Handlers exist for `PipeOperatorModelChoiceError`, `PipeOperatorModelAvailabilityError`, `ModelDeckPresetValidatonError`, `ValidateBundleError`, `InferenceSetupRequiredError`, `TelemetryConfigValidationError`, the gateway-config family, and the remote-config family.

`ErrorContext` (a `StrEnum`) describes where the error happened: `PIPE_RUN`, `VALIDATION`, `BUILD`, plus pre-validation contexts.

### Agent CLI — JSON and markdown

`pipelex/cli/agent_cli/commands/agent_output.py` defines:

- `CliOutputFormat` (`StrEnum`): `JSON`, `MARKDOWN`.
- A module-level `ContextVar` (`_agent_cli_output_format`) with `set_agent_cli_output_format()` / `get_agent_cli_output_format()` — set once per invocation from the command's `--format` option, so every downstream `agent_success` / `agent_error` call inherits it without threading the format argument through.
- `agent_error(message, error_type, cause, **extra)` — dispatches on the active format: JSON to stderr via `_agent_error_json`, or markdown to stderr via `agent_error_markdown`. Both `raise typer.Exit(1) from cause`.
- `agent_success(result)` — JSON or markdown to stdout, same dispatch.
- `extract_validation_errors(exc: ValidateBundleError)` — flattens blueprint / factory / validation / instantiation errors into a list per-category. This is the most structured error delivery in the codebase and remains the reference shape.

The JSON error payload:

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

`agent_error()` reads `cause.to_error_report()` when `cause` is a `PipelexError` and pulls `user_action`, `retryable`, `error_category`, `error_domain`, `model`, `provider` from the report. The string-keyed dicts (`AGENT_ERROR_HINTS`, `AGENT_ERROR_DOMAINS`, `RETRYABLE_ERROR_TYPES`) are consulted only as a fallback when the report has no value — see [track-metadata-model.md](track-metadata-model.md) for the migration of dict entries onto the classes.

`_build_error_source(exc)` walks the `__cause__` chain and emits `"ExceptionType @ filename:line (in function)"`, prioritizing frames inside `/pipelex/` over `.venv/` frames.

### Agent CLI — format coverage

`--format markdown|json` is wired on `run`, `validate`, `init`, `models`, `doctor`, and `check-model`, with **markdown as the default**. The error path inherits the same option via the `ContextVar`. `inputs` / `concept` / `pipe` / `fmt` / `lint` stay JSON-only. The contract is documented in `pipelex/cli/agent_cli/CLAUDE.md`.

`InferenceSetupRequiredError` is a markdown-by-default special case independent of `--format`: it renders setup-guidance to stdout with exit 0 (used by agent skills on first run).

### Validation error special case

`ValidateBundleError` (defined in `pipelex/pipeline/validate_bundle.py`) aggregates four error sources:

1. Blueprint validation errors (from interpreter).
2. Pipe factory errors (e.g. missing concepts).
3. Pipe validation errors (e.g. missing inputs, type mismatches).
4. Pipe / concept instantiation errors (pydantic validation during factory).

`extract_validation_errors` returns a flat list of dicts, each with at minimum `category`, `error_type`, and `message`, plus contextual fields per category. The Rich path uses `_display_validation_error_details` in `pipelex/cli/error_handlers.py` to render the same structure as styled blocks.

## HTTP-status mapping (authoritative)

`pipelex` is a library — there is no API server in the package. But the HTTP API repos (`pipelex-relay`, `pipelex-back-office`) must render an `ErrorReport` as an HTTP response, and the `error_domain` → status mapping was being reinvented per repo. The mapping lives in the library, in `pipelex/base_exceptions.py`:

- `error_domain_to_http_status(error_domain)` — the pure domain → status table: `INPUT` → 422, `CONFIG`/`RUNTIME` → 500, `None` (or an unrecognized string) → 500.
- `ErrorReport.http_status` — the full property: a provider 429 (`provider_metadata.status_code == 429`) takes precedence so the API can emit a `Retry-After` header from `provider_metadata.retry_after_seconds`; otherwise it follows `error_domain`.

The library stays HTTP-agnostic — no web-framework import, only the mapping table. Downstream FastAPI exception handlers call `ErrorReport.http_status` and are a trivial adapter; they must not redefine the contract.

## Open gaps

None for delivery itself. The remaining work is the metadata migration in [track-metadata-model.md](track-metadata-model.md): while delivery reads `to_error_report()` first, several `PipelexError` subclasses still depend on the fallback dicts because they carry no class-level `error_domain` / `user_action`.

## Related tracks

- [track-metadata-model.md](track-metadata-model.md) — `to_error_report()` is the canonical data source for both delivery paths; the dict fallback it discusses is the metadata that feeds these renderers.
- [track-testing.md](track-testing.md) — the full-chain integration snapshot and the Rich-panel snapshot tests that cover this track.
