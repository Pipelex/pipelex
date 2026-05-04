# Worker Error Handling — Phase 4: Markdown-Default Agent CLI Output

> Reference: `wip/worker-error-handling-review.md` for the full review of current state.
> Completed phases (0–3) archived in `wip/error-handling-phases-0-3-completed.md`.

---

## Definition of DONE

A phase is done when **all** of the following are true:

1. **All workers catch SDK-specific exceptions** and wrap them in domain exceptions with `from exc`, model descriptor in message, and error category assigned
2. **`make agent-check` passes** (pyright, mypy, ruff)
3. **`make agent-test` passes** (full test suite green)
4. **New unit tests exist** for each changed error path — tests verify:
   - The correct custom exception type is raised
   - The error category is set correctly
   - The error message includes model descriptor
   - The `from exc` chain is preserved
   - The `to_error_report()` output matches the expected JSON schema
5. **CLI `--format json` error output** is tested with snapshot tests for representative error types
6. **Temporal compatibility verified**: `TemporalError.from_message_exception()` correctly extracts error category and maps to `non_retryable` based on category, tested with unit tests
7. **Agent CLI** `agent_error()` updated to use structured fields from exceptions rather than lookup dicts, tested

---

## Phase 4: Markdown-Default Agent CLI Output

> Make all agent CLI commands return markdown by default, with `--format json` for structured output.
> Currently `models`, `doctor`, `check-model` already support this. This phase extends it to
> `run`, `validate`, and error output. Commands where JSON IS the payload (`inputs`, `concept`,
> `pipe`) are excluded -- their output format is inherent to the command's purpose.
>
> **Scope:**
> - `run` (pipe, bundle, method): success output as markdown, `--format json` for structured
> - `validate` (pipe, bundle, method): success output as markdown, `--format json` for structured
> - `agent_error()`: markdown by default to stderr, `--format json` for structured
> - `init`: success output as markdown (simple confirmation)
> - **Excluded:** `inputs` (returns JSON template), `concept`/`pipe` (returns TOML), `fmt`/`lint` (passthrough)

- [ ] **4.1** Add `agent_error_markdown()` function to `agent_output.py`
  - Markdown rendering of errors, parallel to `agent_error()` which remains the JSON path
  - Format: heading with error type, message body, hint as a tip callout, error_source as code block
  - Must still print to stderr and `raise typer.Exit(1) from cause`

- [ ] **4.2** Add format-aware error dispatch
  - Introduce a way for commands to pass the current `CliOutputFormat` to the error path
  - Options: thread-local / context var, or pass format explicitly to a new `agent_error_dispatch(format, ...)` wrapper
  - `agent_error()` (JSON) and `agent_error_markdown()` are the two backends
  - Keep `agent_error()` as the default when format is unknown (e.g., errors during init before format is parsed)

- [ ] **4.3** Add `--format` option to `run` commands
  - Add `output_format: CliOutputFormat = CliOutputFormat.MARKDOWN` option to `pipe_cmd.py`, `bundle_cmd.py`, `method_cmd.py`
  - Follow existing pattern from `models_cmd.py`: `match/case` on format
  - JSON path: existing `agent_success(result)` unchanged
  - Markdown path: new `_format_run_markdown(result)` function
  - Run markdown should render: main_stuff content (markdown representation if available, else formatted JSON), output file path, graph file path

- [ ] **4.4** Add `--format` option to `validate` commands
  - Same pattern as 4.3 for `validate/pipe_cmd.py`, `bundle_cmd.py`, `method_cmd.py`
  - Markdown path: new `_format_validate_markdown(result)` function
  - Validate markdown should render: pass/fail summary, list of validated pipes with status, error details if any

- [ ] **4.5** Add `--format` option to `init` command
  - Same pattern for `init_cmd.py`
  - Markdown path: simple confirmation with target dir, backends enabled, routing profile

- [ ] **4.6** Wire format into error handlers in `agent_cli_factory.py`
  - `make_pipelex_for_agent_cli()` catches init errors before format is known -- keep JSON for these
  - Command-level error handlers should respect the format option

- [ ] **4.7** Update `agent_cli/CLAUDE.md` to document the new output contract
  - Default format is markdown for all commands except inputs/concept/pipe/fmt/lint
  - `--format json` available on run, validate, init, models, doctor, check-model
  - Errors respect the same format option
  - Document the markdown structure for each command

- [ ] **4.8** Tests for Phase 4
  - Test that `run` with no `--format` produces markdown to stdout
  - Test that `run --format json` produces valid JSON to stdout
  - Test that `validate` with no `--format` produces markdown
  - Test that errors produce markdown to stderr by default
  - Test that errors with `--format json` produce JSON to stderr
  - Test that `inputs` command is unaffected (always JSON)
