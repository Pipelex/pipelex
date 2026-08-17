# Follow-up brief — a broken configuration file should fail like a configuration error, on both CLIs

Two items found while polishing the boot's configuration error messages on `feature/Backend-surface` (S7b, PR #1116) and **deliberately left out of that branch**. They are independent of the fourth migration surface and of each other. This brief is written from what was measured during that session; the agent picking it up should do the actual exploration — grep every site, read every handler, run every scenario — rather than trust the site lists below as complete.

**Where this stands relative to the branch that found it.** S7b fixed four error-message defects on the boot's *validation* path: the unreachable `except`, the `[defaults]` header silence, the loader's own sentence being reduced to the pydantic analysis, and a bad value in `backends.toml` escaping as a bare pydantic error. All of those are about a file that **parses** and then **fails validation**. Neither item here touches that path; both are about what happens *around* it. Do them after S7b lands, so nothing rebases across the boot handler while it is under review.

## Item 1 — a TOML *syntax* error in a configuration file is classified as the user's *input* being wrong

### What was measured

Append `[broken\nfoo = 1` to `~/.pipelex/pipelex.toml` in an isolated fake home (an empty project dir as cwd, so the repo's own `.pipelex/` does not shadow it), then:

- `pipelex show backends` → a Rich traceback panel of a few dozen frames, then the one useful line: `TomlError: TOML parsing error in file '…/.pipelex/pipelex.toml': Expected ']' at the end of a table declaration`.
- `pipelex-agent models --format json` → a proper JSON envelope, **but** with `"error_type": "TomlError"`, **`"error_domain": "input"`**, and the hint *"Initialization failed. Run 'pipelex-agent doctor' to diagnose, or 'pipelex init config' to reset configuration"*.

The same happens for `backends.toml` and for a per-backend file under `inference/backends/` (measured on `ollama.toml`); it is uniform across surfaces because nothing between `load_toml_from_path` and the CLI root catches `TomlError` for a configuration file.

### Why it is wrong, not merely unpolished

- **`error_domain` is the contract field.** The agent-hook specification branches on it (see the workspace-root `CLAUDE.md` § *Surface output conventions*, and `docs/specs/` for the hook pipeline). `input` says *the input you gave this run was wrong*; a broken `pipelex.toml` is `config`. An agent following the spec will treat its own request as the mistake.
- **The hint is the "start over" advice S7b spent two fixes removing** from the migration path: `pipelex init config` resets every file, and the honest hint is *fix line N of this file*.
- **The position is dropped from the message.** `pipelex/tools/misc/toml_utils.py::load_toml_from_path` composes the message from `exc.msg` — the bare tomli message — and stores `lineno`/`colno` on the `TomlError` as attributes only. The user reads "Expected ']' at the end of a table declaration" with no line. (Memory note `reference_tomli_vs_tomllib_error_attrs` is about this attribute surface: stdlib `tomllib` exposes them only from 3.14; we are on `tomli`.)

### Where the classification comes from

`pipelex/cli/agent_cli/commands/agent_output.py` maps `"TomlError"` → `"input"` in its error-domain table (line ~186 at the time of writing) and carries a `TomlError` hint (line ~155). That mapping is **right** for the other producers of `TomlError` — an inputs file (`cli/commands/run/_run_core.py`, `agent_cli/commands/run/stdin_resolver.py`) or a `.mthds` bundle (`mthds_parsing/parser.py` catches it) — and wrong only for a configuration file. **The CLI cannot tell those apart by class; only the loader that opened the file knows which kind it was.** So the fix is not in `agent_output.py`.

### What to do

Convert `TomlError` into that surface's own configuration error **at each configuration loader**, naming the file *and the line and column*, so it arrives at both CLIs as a `PipelexConfigError`-family error with `error_domain = config` and the same shape as a validation refusal — including being catchable by the boot's existing arms (`CONFIG_REFUSED` for the main config in `runtime_boot.py`, `BACKEND_LIBRARY_REFUSED` for the backend library) so the human CLI message builder and `raise_config_setup_error` see it like any other refusal.

Sites known from the session (**verify by grepping callers of `load_toml_from_path` / `load_toml_from_path_if_exists` under `pipelex/system/configuration/`, `pipelex/system/telemetry/`, `pipelex/system/pipelex_service/`, `pipelex/cogt/model_backends/`, `pipelex/cogt/models/`, `pipelex/cogt/routing/` — the list below is what was seen, not a census**):

- the main configuration tiers (`ConfigLoader` in `pipelex/system/configuration/config_loader.py` — this is the one whose refusal is `ConfigValidationError`, and it should keep raising in that family so `CONFIG_REFUSED` catches it);
- `telemetry.toml` and `pipelex_service.toml` loaders;
- `backends.toml` (`InferenceBackendLibrary.load`, the `load_toml_from_path` at the top — today it catches only `FileNotFoundError` there; the right class is `InferenceBackendLibraryValidationError`, which S7b just gave its first real raise site, or a sibling — decide whether "does not parse" and "does not validate" want distinct classes for the doctor's per-backend probe, which greps messages);
- per-backend model-spec files (`_load_local_model_specs`, same file) and the gateway local override (`load_toml_from_path_if_exists` in `_load_gateway_model_specs`);
- routing profiles and model decks (their loaders were not opened during the session — check whether they go through the same helper).

Decide once whether the position goes into the message at `load_toml_from_path` itself (one site, every consumer benefits — but check the `.mthds` parser and the inputs-file paths, which may already append it) or per loader.

### What must not change

- A configuration that will not *parse* has no ledger story: the migration engine reads the document with tomlkit and a file that will not parse is a `blocked_reason` in its plan already (`FileBlockedReason` — check the enum for the parse-failure member). Do not try to route a syntax error through `report_validation_error`'s scan; there is nothing to scan. It is a plain configuration error with a file and a line.
- Boot tolerance (`replay_surface_files_in_memory`) must not attempt to replay an unparseable file. Confirm the retry declines cleanly rather than raising something new; the rule from S7b is that nothing that goes wrong inside the retry may replace the error the user already has.
- The other `TomlError` producers keep `error_domain = input`. Add a test on the agent CLI that a broken inputs file still reports `input` and a broken `pipelex.toml` reports `config` — that pair is the whole point.

### Tests to write

- Per surface, a unit test that plants a syntax error and asserts the loader raises the surface's config error naming the file and the line — from the real loader, never a hand-built exception (memory: `reference_a_hand_built_exception_cannot_prove_a_handler_catches_it`).
- The agent-CLI domain pair above.
- Mutation-check the boot: narrow the arm back and watch the syntax case go red.

## Item 2 — the human CLI renders every boot configuration failure as a traceback

### What was measured

Every configuration failure that leaves the boot as `PipelexSetupError` or `PipelexConfigError` — the stale-file message with its migration block, the model/backend/file sentence S7b just restored, a bad value in `backends.toml` — prints in the human CLI as **a Rich traceback panel with the message underneath**. The messages are good now; the reader finds them at the bottom of forty frames of `runtime_boot.py` / `cli_factory.py`.

`pipelex/cli/cli_factory.py::make_pipelex_for_cli` catches a hand-picked list — `InferenceSetupRequiredError`, `TelemetryConfigValidationError`, `GatewayTermsNotAcceptedError`, `GatewayApiKeyMissingError`, `GatewayDoNotTrackConflictError`, `RemoteConfigUnavailableError`, `RemoteConfigValidationError`, `GatewayUnknownModelError` — and routes each to a handler in `pipelex/cli/error_handlers.py` (`display_error_panel`, and per-class handlers). `PipelexSetupError` and `PipelexConfigError` are **not on the list**, so they fall through to typer's pretty-exception rendering (`pretty_exceptions_show_locals=False` in `pipelex/cli/_cli.py`). `error_handlers.py` already has the machinery the fix wants: `display_error_panel`, `set_traceback_requested` / `is_traceback_requested`, `print_traceback_if_requested` — a `--traceback` flag exists precisely so that the default is a panel and the traceback is opt-in.

This is **not** TOML-specific and not S7b-specific; item 1 merely lands one more class in the same gap.

### What to do

Route boot configuration failures through the panel: catch the `PipelexConfigError` / `PipelexSetupError` family in `make_pipelex_for_cli` (or wherever the exploration shows the single right boundary is — check the agent CLI's equivalent factory too, which already produces an envelope, to keep the two roots symmetric), display the message in the panel, print the traceback only when `--traceback` was requested, and exit non-zero the way the other handlers do.

Things to settle during exploration, not assumed:

- **Which classes.** `PipelexConfigError` carries the structured `migration` block; the panel should render the message (which already contains the migration paragraph) and need not render the block separately — but confirm nothing else in the human CLI was reading the block. `PipelexSetupError` is what the boot raises for the late components (backend library, model deck, routing profiles); it may carry no block.
- **Whether the doctor's boot paths are affected.** `doctor_cmd.py` catches `CONFIG_REFUSED` itself in two places and `PipelexConfigError` in a third; those are its own presentation and should stay.
- **The exit code and the `--traceback` interplay** — follow what the existing handlers do; do not invent a second convention.
- **The tests that pin today's rendering.** Some CLI tests may assert on a traceback or on `SystemExit` shape; find them before changing the boundary.

### Tests to write

- A CLI-level test per family (a stale/wrong config → panel with the message, no traceback; same with `--traceback` → traceback present).
- Nothing about message *content* — that is pinned one layer down already (`tests/unit/pipelex/test_runtime_boot_stale_backend_error.py`, `tests/unit/pipelex/core/test_validation_report.py`).

## Suggested order and scope

1. **Item 1 first**, one PR, `fix/` prefix against `dev`. It is a correctness fix (a wrong `error_domain`) with a small mechanical footprint; it also carries the position into the message. Changelog under *Fixed*; docs: `docs/migration-ledger.md` § *Reporting a stale configuration on a validation error* has a sentence about which loaders report through the scan — say in one line that a file that does not parse is a plain configuration error and is not scanned. Update the agent-CLI output docs if the `TomlError` hint text changes.
2. **Item 2 second**, its own PR, `fix/` or `chore/`. Presentation only; changelog under *Fixed* or *Changed* depending on what the exploration finds about exit codes.

Neither blocks a release, and neither should be folded into S7b.

## Reproduction harness

The session's fake home is a scratchpad copy that will not survive; rebuild one: a temp `HOME` with `.pipelex/` populated by `printf 'y\n' | env HOME=<tmp> pipelex init config`, an **empty** project directory as cwd (the repo root has its own `.pipelex/inference/backends/` and wins the whole directory), and `pipelex show backends` as the command that boots through every library. Plant faults with an editor, never in `~/.pipelex/` — the real one is a stale specimen kept for the release step (see `TODOS.md` on `feature/Backend-surface`, *Rules of engagement*).
