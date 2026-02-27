# Agent CLI (`pipelex-agent`)

Machine-first CLI for running and validating Pipelex method bundles (`.mthds` files). All output is structured JSON to stdout (success) or stderr (error). No Rich formatting, no interactive prompts.

## Companion: Agent Skills

The CLI is consumed by 7 Claude skills defined in a separate repo. Changes to the CLI often require corresponding skill updates, and vice versa.

- Skills repo: `../agent-skills/skills/` (relative to project root)
- Skills: `run`, `check`, `edit`, `fix`, `explain`, `synthesize-inputs`
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
  run/                         # run — execute pipeline (pipe|bundle|method subcommands)
    app.py                     # run_app Typer, subcommand registration
    pipe_cmd.py                # run pipe — execute by pipe code
    bundle_cmd.py              # run bundle — execute from bundle file/directory
    method_cmd.py              # run method — execute installed method
    _run_core.py               # Shared async run logic (local runner)
    _run_core_api.py           # Shared async run logic (API runner)
    _output_helpers.py         # Output formatting helpers
    stdin_resolver.py          # Stdin input resolution
  validate/                    # validate — verify pipes/bundles/methods
    app.py                     # validate_app Typer, subcommand registration
    pipe_cmd.py                # validate pipe — validate by code, or --all
    bundle_cmd.py              # validate bundle — validate bundle file/directory (+ --graph)
    method_cmd.py              # validate method — validate installed method
    _validate_core.py          # Shared validation logic
  inputs/                      # inputs — generate example input JSON
    app.py                     # inputs_app Typer, subcommand registration
    pipe_cmd.py                # inputs pipe — inputs for a pipe by code
    bundle_cmd.py              # inputs bundle — inputs from bundle file/directory
    method_cmd.py              # inputs method — inputs for installed method
    _inputs_core.py            # Shared inputs logic
  fmt_cmd.py                   # fmt — format file via plxt passthrough
  lint_cmd.py                  # lint — lint file via plxt passthrough
  plxt_passthrough.py          # Shared helper for plxt subprocess delegation
  concept_cmd.py               # concept — JSON spec → concept TOML
  pipe_cmd.py                  # pipe — JSON spec → pipe TOML
  assemble_cmd.py              # assemble — combine TOML parts into .mthds
  models_cmd.py                # models — list presets, aliases, talent mappings
  doctor_cmd.py                # doctor — config health check
```

## Commands

| Command | Does |
|---------|------|
| `run` | Executes a pipeline (pipe\|bundle\|method subcommands), returns JSON with main_stuff + working_memory. Graph visualizations on by default (`--no-graph` to disable). |
| `validate` | Dry-runs pipes/bundles/methods (pipe\|bundle\|method subcommands), returns validation status per pipe. Bundle subcommand supports `--graph` for graph visualization. |
| `fmt` | Formats a .mthds/.toml/.plx file in-place (delegates to plxt) |
| `lint` | Lints a .mthds/.toml/.plx file for errors (delegates to plxt) |
| `inputs` | Generates example input JSON for a pipe/bundle/method (pipe\|bundle\|method subcommands) |
| `concept` | Converts a JSON concept spec into TOML |
| `pipe` | Converts a JSON pipe spec (typed) into TOML |
| `assemble` | Merges concept + pipe TOML sections into a complete `.mthds` file |
| `models` | Lists available model presets, aliases, waterfalls, and talent mappings |
| `doctor` | Checks config, credentials, models health |

## Key Patterns

- **Output contract**: Every command returns via `agent_success(dict)` or `agent_error(message, error_type, cause)`. Never print outside these. Exception: `fmt` and `lint` are raw passthrough to `plxt` — they bypass `agent_success()`/`agent_error()` intentionally so the calling tool can parse native output.
- **Error classification**: Each error type maps to a domain (`input`, `config`, `runtime`), a hint string, and a `retryable` flag. See `AGENT_ERROR_HINTS` dict in `agent_output.py`.
- **Init**: All commands that need Pipelex use `make_pipelex_for_agent_cli(library_dirs)`. It catches init errors and routes them through `agent_error()`.
- **Async core**: Run and validate are async — commands use `asyncio.run()`.
- **File convention**: Generated outputs go to `pipelex-wip/` with incremental naming (`pipeline_01/`, `pipeline_02/`).
- **TOML handling**: Uses `tomlkit` (not `tomllib`) to preserve formatting and inline tables.
