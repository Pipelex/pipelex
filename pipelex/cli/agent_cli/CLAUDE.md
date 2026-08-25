# Agent CLI (`pipelex-agent`)

Machine-first CLI for running and validating Pipelex method bundles (`.mthds` files). No Rich formatting, no interactive prompts.

## Output format

Two independent options control the two output streams:

- `--format markdown|json` — **success/useful output**. Defaults to markdown. Accepted by `run`, `validate`, `fix`, `init`, `models`, `check-model`, `doctor`, `codegen types`, `codegen check`. Goes to stdout. Threaded explicitly to `agent_success_formatted()` from each command function — no hidden state.
- `--error-format markdown|json` — **error reporting** (stderr). Optional. When omitted, **inherits the value of `--format`**, so `--format json` still flips both as it did historically. Accepted by the same commands as `--format`.

Only the error format is backed by a module-level `ContextVar` in `agent_output.py` (`_agent_cli_error_format`). The reason: `agent_error()` is called from sites that don't see the Typer option — factory init failures (`agent_cli_factory.py`), the unknown-command handler in `PipelexAgentCLI.get_command`, runner validation in the app callback, and any future site in shared library/runtime code. The ContextVar lets all of them honor `--error-format` (or `--format`'s inherited value) for free. JSON is the default so errors raised before any command opts in stay machine-parseable.

`concept`, `pipe`, `fmt`, `lint`, `accept-gateway-terms` are **always JSON / raw passthrough** — they have neither `--format` nor `--error-format`. Their errors keep flowing through the ContextVar's JSON default.

`inputs` is a deliberate deviation: its `--format` takes `json|toml` (an `InputsTemplateFormat`, NOT the `markdown|json` `CliOutputFormat` pair) because it selects the **template serialization**, not a presentation style. `json` (default) keeps the structured success envelope; `toml` prints the raw TOML template to stdout, in the same spirit as the `concept`/`pipe` raw-TOML passthrough. A pipe with no inputs prints a TOML comment line in `toml` mode (valid TOML, loads back as an empty dict). `inputs` still has no `--error-format` — its errors keep flowing through the ContextVar's JSON default.

Markdown structure per command:

- `run`: `# Pipeline run complete`, a `## Result` section (the rendered `main_stuff` markdown with `--with-memory`, otherwise the concept JSON in a fenced block), and output / graph file paths. Cost is machine-first: on the local runner, when costs are on (`--costs`, the default) and the run did reportable work (any tokens or any cost), a best-effort `cost_report` object (`{total_cost, by_model: [...]}`, real USD) rides the JSON `--with-memory` envelope — there is **no** Rich cost table on stderr (unlike the human `pipelex run` CLI). The markdown renderer ignores the `cost_report` key, so it is JSON-only. A free/zero-price model still reports its token usage (with `total_cost` 0). The `cost_report` is **absent** when the run did no reportable work (dry runs), when `--no-costs` is passed, on the API-runner path (which does not assemble local usage), or if cost-summary aggregation fails (caught and skipped so it never fails an otherwise-successful run) — so consumers must treat it as optional.
- `validate`: `# Validation passed`, the bundle path when relevant, and a list of validated pipes with their status. Every entry in `validated_pipes` (markdown and JSON) identifies its pipe by the namespaced `pipe_ref` (`domain.code`) — the same unambiguous identity across `validate all`, `validate bundle`, and `validate pipe`, so the same pipe is never reported under two identifiers. `validate bundle`, `validate method`, and `validate all` carry `pending_signatures` — the library-wide list of pipes still declared as `PipeSignature` (unimplemented forward declarations), namespaced by `pipe_ref` — rendered as a "Pending signatures" section in markdown. They also carry a derived `is_runnable` boolean (`true` ⇔ `pending_signatures` is empty), and the markdown adds an explicit plain-English runnability verdict on those surfaces: a complete bundle/library states it is runnable, while one with pending signatures states it is NOT yet runnable immediately above the verbatim "Pending signatures" heading. These whole-bundle/whole-library surfaces are **strict by default**: they exit non-zero on `not is_runnable` unless `--allow-signatures` is passed (which both tolerates the placeholders for the exit code and mock-runs the signature pipes in the sweep). Single-pipe surfaces make no library-wide runnability claim and never gate the exit code on it: bare `validate pipe <code>` omits the key and emits no verdict, while `validate bundle`/`validate method` with `--pipe` still surface the library-wide `pending_signatures` for information but do not gate on it (the requested slice can be fully implemented even when unrelated placeholders remain elsewhere). The whole-bundle and whole-library surfaces also carry a `warnings` array — the advisory lints, rendered as a "Warnings" section in markdown — assembled by `pipelex/pipeline/advisory_warnings.py`, the ONE composition point every advisory-bearing channel calls (this CLI, the bare CLI, the builder ops and the protocol report). Bare `validate pipe <code>` carries none, and neither does the builder's `validate_all`; `validate bundle` / `validate method` with `--pipe` DO carry them, because they validate the whole bundle and only narrow the dry run, so the array stays bundle-wide there. Add a new advisory family there, never at a call site: the sites used to assemble their own and disagreed about which families they carried.
- `fix`: `# Fix applied - bundle is valid` after one or more fixes, `# Bundle already valid` when the loop had nothing to apply, or `# Bundle valid but not runnable` when pending `PipeSignature` placeholders remain. The JSON success envelope carries `is_valid`, `bundle_path`, `iterations`, `fixes_applied`, `files_written`, `remaining_errors`, and, on successful validation, `pending_signatures` plus `is_runnable`. Whole-bundle fix runs are strict by default: they emit the success envelope but exit 1 on `not is_runnable` unless `--allow-signatures` is passed. A still-invalid verdict exits 1 via `FixBundleError` on stderr with the same structured result fields plus any `bail_reason`.
- `migrate`: `# Configuration migration`, the mode (applied / dry run) and verdict, the directories walked, a files-walked/changed/written count, then one `## <path>` section per file that is not clean listing the entries applied, the entries blocked with their reason and guidance, and any unexplained paths. Paths, operation kinds and ledger-supplied values only — no value read from the user's file is ever rendered, in either format.
- `init`: `# Pipelex initialized` with target directory, enabled backends, and routing profile.
- error path: `# Error: <error_type>`, the message, the hint as a `> 💡` callout, and a `## Details` section. `error_source` (internal stack frames) is omitted from markdown — it remains in the JSON envelope (`--error-format json`) for programmatic consumers.

## Companion: Agent Skills

The CLI is consumed by a set of Claude skills defined in a separate repo. Changes to the CLI often require corresponding skill updates, and vice versa.

- Skills location: `../mthds-plugins/mthds/skills/` (relative to project root) — one `mthds-*` directory per skill
- Each skill is a `SKILL.md` with optional `references/` dir
- Shared reference docs: `../mthds-plugins/mthds/skills/shared/` (`error-handling.md`, `mthds-agent-guide.md`, `mthds-reference.md`, `native-content-types.md`, …)

When changing CLI command signatures, output schemas, or error types, check whether the affected skills need updating.

## Code Layout

```
_agent_cli.py                  # Typer app setup, version callback, PipelexAgentCLI(TyperGroup) — command registration, ordering
commands/
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
  fix/                         # fix — deterministic in-place bundle fixes
    app.py                     # fix_app Typer, subcommand registration
    bundle_cmd.py              # fix bundle — run validate/fix/re-validate loop
  inputs/                      # inputs — generate example input JSON
    app.py                     # inputs_app Typer, subcommand registration
    pipe_cmd.py                # inputs pipe — inputs for a pipe by code
    bundle_cmd.py              # inputs bundle — inputs from bundle file/directory
    method_cmd.py              # inputs method — inputs for installed method
    _inputs_core.py            # Shared inputs logic
  codegen/                     # codegen — crate projections + offline drift check
    app.py                     # codegen_app Typer, subcommand registration
    types_cmd.py               # codegen types — project the crate's concept set (stamped files + codegen.lock)
    check_cmd.py               # codegen check — offline drift check (pure hashing, no Pipelex boot)
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
| `init` | Initializes Pipelex configuration (non-interactive). Defaults to project `.pipelex/` at detected project root. Use `--global`/`-g` to target `~/.pipelex/`. Accepts `--config`/`-c` with inline JSON or file path for backends, routing (via `primary_backend`), and gateway terms; telemetry is seeded from a template, not `--config`. `--format markdown\|json` (success, default: markdown) + `--error-format markdown\|json` (errors, defaults to `--format`'s value). |
| `run` | Executes a pipeline (pipe\|bundle\|method subcommands), returns main_stuff + working_memory. Graph visualizations on by default (`--no-graph` to disable). `--format markdown\|json` (success, default: markdown) + `--error-format markdown\|json` (errors, defaults to `--format`'s value). |
| `validate` | Dry-runs pipes/bundles/methods (pipe\|bundle\|method subcommands), returns validation status per pipe. Bundle subcommand supports `--graph` for graph visualization (with `--graph-format` for the graph renderer). `--format markdown\|json` (success, default: markdown) + `--error-format markdown\|json` (errors, defaults to `--format`'s value). |
| `fix` | Applies deterministic safe fixes to a bundle file or directory (`fix bundle`) and re-validates until valid, out of fixes, or max iterations. Supports `--allow-signatures`, `--select`, `--ignore`, `--max-iterations`, and `-L/--library-dir`. `--format markdown\|json` (success, default: markdown) + `--error-format markdown\|json` (errors, defaults to `--format`'s value). |
| `fmt` | Formats a .mthds/.toml/.plx file in-place (delegates to plxt) |
| `lint` | Lints a .mthds/.toml/.plx file for errors (delegates to plxt) |
| `inputs` | Generates an example inputs template for a pipe/bundle/method (pipe\|bundle\|method subcommands). `--format json\|toml` (template serialization, default: json — NOT the markdown\|json pair); `toml` prints raw TOML to stdout |
| `codegen` | Agent mirror of the bare `pipelex codegen` family (types\|check subcommands). `types --target <flavor>` resolves the closure into the normalized crate and writes stamped typed artifacts + `codegen.lock` (write-if-changed); `check` is the offline drift check (pure hashing, no Pipelex boot — exit 0 current, 1 drift as a structured `CodegenDriftError` with `drifts[]`, 2 no/unreadable lock). Both: `--format markdown\|json` (success, default: markdown) + `--error-format markdown\|json` (errors, defaults to `--format`'s value). |
| `concept` | Converts a JSON concept spec into raw TOML (stdout) |
| `pipe` | Converts a JSON pipe spec into raw TOML (stdout). A spec with a `type` (via `--type` or a `type` key) is that concrete pipe; a **typeless** spec (no `type`) is a signature and renders a `[pipe.x]` section with no type line. An explicit `type = "PipeSignature"` is rejected with a migration error — `PipeSignature` is not a type. |
| `models` | Lists available model presets, aliases, and waterfalls. `--format markdown\|json` (success, default: markdown) + `--error-format markdown\|json` (errors, defaults to `--format`'s value) |
| `check-model` | Validates a model reference and suggests alternatives if invalid. `--type`/`-t` for model category, `--format markdown\|json` (success, default: markdown) + `--error-format markdown\|json` (errors, defaults to `--format`'s value) |
| `migrate` | Migrates this machine's configuration files (global `~/.pipelex/` and project `.pipelex/`, non-recursively) to the current schema by replaying each surface's ledger. Does **not** boot — it is the command for a configuration that cannot load. Writes only with `--yes`; `--dry-run` plans and is the default; the two together are refused with exit 2. `--format markdown\|json` (success, default: markdown) + `--error-format markdown\|json`. The verdict is the structured `needs_attention`, not the exit code. |
| `doctor` | Checks config, credentials, models health. `--global`/`-g` for global dir. `--format markdown\|json` (success, default: markdown) + `--error-format markdown\|json` (errors, defaults to `--format`'s value). The telemetry check carries a `finding` (`healthy`/`not_found`/`unparseable`/`out_of_date`/`invalid`) beside its `healthy` and `message`; branch on that, and note `out_of_date` is `pipelex migrate`'s and never `pipelex init telemetry`'s — a reset would discard the settings the migration keeps — and that it means the migration would actually rewrite that file, so a file it would only report on is `invalid`. `checks.pending_migrations` is the machine-wide half: a `finding` (`up_to_date`/`pending`/`needs_attention`/`unavailable`) plus `migratable_files` and `attention_files`. It is the only channel a machine has for a pending migration — a tolerated boot warns a person and this CLI silences logging — and it is **not** scoped by `--global`, because it answers for `pipelex migrate`, which walks both directories. |

## Key Patterns

- **Output contract**: Commands with `--format` emit success via `agent_success_formatted(result, markdown_renderer, output_format)` — JSON or a markdown renderer per the explicit `output_format` argument. `agent_error(message, error_type, cause)` dispatches JSON or markdown by reading the `_agent_cli_error_format` ContextVar, which each `--format`-aware command sets via `set_agent_cli_error_format(error_format or output_format)` at function entry. Exceptions that print directly to stdout: `fmt`/`lint` (plxt passthrough), `concept`/`pipe` (raw TOML). Markdown renderers: `format_run_markdown` (`run/_output_helpers.py`), `format_validate_markdown` (lifted to the non-CLI `pipelex/pipeline/validation_render.py` so `pipelex-api` can import it without CLI/Typer deps), `format_fix_markdown` (non-CLI `pipelex/pipeline/fixes/fix_render.py`), `_format_init_markdown` (`init_cmd.py`).
- **Error classification**: Each error type maps to a domain (`input`, `config`, `runtime`), a hint string, and a `retryable` flag. See `AGENT_ERROR_HINTS` dict in `agent_output.py`. The `error_domain` also drives the HTTP-status mapping for downstream APIs — see `error_domain_to_http_status()` in `pipelex/base_exceptions.py`.
- **The `migration` field on a configuration error**: A `PipelexConfigError` carries one when a scan of this machine's configuration directories found something — and only then, so its presence is the test for whether the migration history has anything to say. Whether a command *repairs* it is the separate `would_write` field: true means the configuration is *old*, and the loop is `pipelex-agent migrate --dry-run --format json`, show the user, then `--yes`; false means the block is a diagnosis its `plans` carry and the command would rewrite nothing, so branching on presence alone sends an agent to a run with nothing to do. Its `plans` are the same shape that command emits under its own `plans` key. `error_domain` stays `config`: a domain the hook specification does not know routes to BLOCK, which would stop an agent instead of telling it what to run. See `docs/migration-ledger.md` → "Reporting a stale configuration on a validation error".
- **Init**: All commands that need Pipelex use `make_pipelex_for_agent_cli(library_dirs)`. It catches init errors and routes them through `agent_error()`.
- **Async core**: Run and validate are async — commands use `asyncio.run()`.
- **File convention**: Generated outputs go to `mthds-wip/` with incremental naming (`pipeline_01/`, `pipeline_02/`).
- **TOML handling**: Uses `tomlkit` (not `tomllib`) to preserve formatting and inline tables.
