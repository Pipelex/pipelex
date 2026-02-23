# Agent CLI (`pipelex-agent`)

Machine-first CLI for building, running, and validating Pipelex method bundles (`.mthds` files). All output is structured JSON to stdout (success) or stderr (error). No Rich formatting, no interactive prompts.

## Companion: Agent Skills

The CLI is consumed by 7 Claude skills defined in a separate repo. Changes to the CLI often require corresponding skill updates, and vice versa.

- Skills repo: `../agent-skills/skills/` (relative to project root)
- Skills: `build`, `run`, `check`, `edit`, `fix`, `explain`, `synthesize-inputs`
- Each skill is a `SKILL.md` with optional `references/` dir
- Shared reference docs: `../agent-skills/skills/shared/` (`error-handling.md`, `pipelex-agent-guide.md`, `pipelex-reference.md`, `prerequisites.md`)

When changing CLI command signatures, output schemas, or error types, check whether the affected skills need updating.

## Code Layout

```
_agent_cli.py                  # Typer app setup, version callback
commands/
  _agent_cli.py                # PipelexAgentCLI(TyperGroup) — command registration, ordering
  agent_output.py              # agent_success(), agent_error(), error hints/domains
  agent_cli_factory.py         # make_pipelex_for_agent_cli() — init with JSON errors
  build_core.py                # BuildPipeResult, BuildPipeError, build_pipe_core()
  build_cmd.py                 # build — generate pipeline from prompt
  run_cmd.py                   # run — execute pipeline
  validate_cmd.py              # validate — verify pipes/bundles/libraries
  fmt_cmd.py                   # fmt — format file via plxt passthrough
  lint_cmd.py                  # lint — lint file via plxt passthrough
  plxt_passthrough.py          # Shared helper for plxt subprocess delegation
  inputs_cmd.py                # inputs — generate example input JSON
  concept_cmd.py               # concept — JSON spec → concept TOML
  pipe_cmd.py                  # pipe — JSON spec → pipe TOML
  assemble_cmd.py              # assemble — combine TOML parts into .mthds
  graph_cmd.py                 # graph — render execution graph HTML
  models_cmd.py                # models — list presets, aliases, talent mappings
  doctor_cmd.py                # doctor — config health check
  mthds_passthrough.py         # Shared helper for mthds subprocess delegation
  mthds_init_cmd.py            # mthds-init — initialize METHODS.toml
  mthds_list_cmd.py            # mthds-list — display package manifest
  mthds_add_cmd.py             # mthds-add — add dependency
  mthds_lock_cmd.py            # mthds-lock — resolve deps, generate lock
  mthds_install_cmd.py         # mthds-install — install from lock
  mthds_update_cmd.py          # mthds-update — re-resolve deps
  mthds_publish_cmd.py         # mthds-publish — publish package
  mthds_validate_cmd.py        # mthds-validate — validate manifest/pipes
```

## Commands

| Command | Does |
|---------|------|
| `build` | Runs BuilderLoop to generate a `.mthds` from a natural language prompt |
| `run` | Executes a pipeline, returns JSON with main_stuff + working_memory. Supports directory mode (auto-detects bundle, inputs, library dir). Graph visualizations on by default (`--no-graph` to disable). |
| `validate` | Dry-runs pipes/bundles, returns validation status per pipe |
| `fmt` | Formats a .mthds/.toml/.plx file in-place (delegates to plxt) |
| `lint` | Lints a .mthds/.toml/.plx file for errors (delegates to plxt) |
| `inputs` | Generates example input JSON for a given pipe |
| `concept` | Converts a JSON concept spec into TOML |
| `pipe` | Converts a JSON pipe spec (typed) into TOML |
| `assemble` | Merges concept + pipe TOML sections into a complete `.mthds` file |
| `graph` | Generates graph visualization (HTML) from a .mthds bundle via dry-run |
| `models` | Lists available model presets, aliases, waterfalls, and talent mappings |
| `doctor` | Checks config, credentials, models health |
| `mthds-init` | Initialize a METHODS.toml package manifest (delegates to mthds) |
| `mthds-list` | Display the package manifest (delegates to mthds) |
| `mthds-add` | Add a dependency to METHODS.toml (delegates to mthds) |
| `mthds-lock` | Resolve dependencies and generate methods.lock (delegates to mthds) |
| `mthds-install` | Install dependencies from methods.lock (delegates to mthds) |
| `mthds-update` | Re-resolve dependencies and update methods.lock (delegates to mthds) |
| `mthds-publish` | Publish package for distribution (delegates to mthds) |
| `mthds-validate` | Validate METHODS.toml and optionally run deeper validation (delegates to mthds) |

## Key Patterns

- **Output contract**: Every command returns via `agent_success(dict)` or `agent_error(message, error_type, cause)`. Never print outside these. Exception: `fmt` and `lint` are raw passthrough to `plxt`, and `mthds-*` commands are raw passthrough to `mthds` — they bypass `agent_success()`/`agent_error()` intentionally so the calling tool can parse native output.
- **Error classification**: Each error type maps to a domain (`input`, `config`, `runtime`), a hint string, and a `retryable` flag. See `AGENT_ERROR_HINTS` dict in `agent_output.py`.
- **Init**: All commands that need Pipelex use `make_pipelex_for_agent_cli(library_dirs)`. It catches init errors and routes them through `agent_error()`.
- **Async core**: Build, run, validate are async — commands use `asyncio.run()`.
- **File convention**: Generated outputs go to `pipelex-wip/` with incremental naming (`pipeline_01/`, `pipeline_02/`).
- **TOML handling**: Uses `tomlkit` (not `tomllib`) to preserve formatting and inline tables.
