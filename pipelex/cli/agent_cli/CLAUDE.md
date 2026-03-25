# Agent CLI (`pipelex-agent`)

Machine-first CLI for running and validating Pipelex method bundles (`.mthds` files). All output is structured JSON to stdout (success) or stderr (error). No Rich formatting, no interactive prompts.

## Companion: Agent Skills

The CLI is consumed by a set of Claude skills defined in a separate repo. Changes to the CLI often require corresponding skill updates, and vice versa.

- Skills repo: `../skills/skills/` (relative to project root)
- Skills: `mthds-build`, `mthds-check`, `mthds-edit`, `mthds-explain`, `mthds-fix`, `mthds-inputs`, `mthds-install`, `mthds-pkg`, `mthds-run`
- Each skill is a `SKILL.md` with optional `references/` dir
- Shared reference docs: `../skills/skills/shared/` (`error-handling.md`, `mthds-agent-guide.md`, `mthds-reference.md`, `native-content-types.md`)

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
  concept_cmd.py               # concept — JSON spec → raw TOML to stdout
  pipe_cmd.py                  # pipe — JSON spec → raw TOML to stdout
  models_cmd.py                # models — list presets, aliases, waterfalls
  check_model_cmd.py           # check-model — validate model reference with fuzzy suggestions
  init_cmd.py                  # init — non-interactive config setup (--global/-g, --config/-c)
  doctor_cmd.py                # doctor — config health check (--global/-g)
```

## Commands

| Command | Does |
|---------|------|
| `init` | Initializes Pipelex configuration (non-interactive). Defaults to project `.pipelex/` at detected project root. Use `--global`/`-g` to target `~/.pipelex/`. Accepts `--config`/`-c` with inline JSON or file path for backends, routing, telemetry, and gateway terms. |
| `run` | Executes a pipeline (pipe\|bundle\|method subcommands), returns JSON with main_stuff + working_memory. Graph visualizations on by default (`--no-graph` to disable). |
| `validate` | Dry-runs pipes/bundles/methods (pipe\|bundle\|method subcommands), returns validation status per pipe. Bundle subcommand supports `--graph` for graph visualization. |
| `fmt` | Formats a .mthds/.toml/.plx file in-place (delegates to plxt) |
| `lint` | Lints a .mthds/.toml/.plx file for errors (delegates to plxt) |
| `inputs` | Generates example input JSON for a pipe/bundle/method (pipe\|bundle\|method subcommands) |
| `concept` | Converts a JSON concept spec into raw TOML (stdout) |
| `pipe` | Converts a JSON pipe spec (typed) into raw TOML (stdout) |
| `models` | Lists available model presets, aliases, and waterfalls. `--format markdown\|json` (default: markdown) |
| `check-model` | Validates a model reference and suggests alternatives if invalid. `--type`/`-t` for model category, `--format markdown\|json` (default: markdown) |
| `doctor` | Checks config, credentials, models health. `--global`/`-g` for global dir. `--format markdown\|json` (default: markdown) |

## Key Patterns

- **Output contract**: Most commands return via `agent_success(dict)` or `agent_error(message, error_type, cause)`. Exceptions that print directly to stdout: `fmt`/`lint` (plxt passthrough), `concept`/`pipe` (raw TOML), `models`/`doctor` in markdown mode. Errors always go via `agent_error()` regardless of format.
- **Error classification**: Each error type maps to a domain (`input`, `config`, `runtime`), a hint string, and a `retryable` flag. See `AGENT_ERROR_HINTS` dict in `agent_output.py`.
- **Init**: All commands that need Pipelex use `make_pipelex_for_agent_cli(library_dirs)`. It catches init errors and routes them through `agent_error()`.
- **Async core**: Run and validate are async — commands use `asyncio.run()`.
- **File convention**: Generated outputs go to `mthds-wip/` with incremental naming (`pipeline_01/`, `pipeline_02/`).
- **TOML handling**: Uses `tomlkit` (not `tomllib`) to preserve formatting and inline tables.
