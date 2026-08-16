---
description: "Use the pipelex-agent CLI for machine-oriented output — designed for AI agents, IDE extensions, and automation toolchains."
---

# Agent CLI (`pipelex-agent`)

The `pipelex-agent` CLI is a machine-oriented companion to the main `pipelex` CLI. It is designed for programmatic consumption by AI agents, IDE extensions, and other automation tools. Output format varies by command — markdown or JSON, raw TOML, or `plxt` passthrough — with no Rich formatting or interactive prompts. Structured commands emit errors to stderr; the error format is controlled by `--error-format`, which defaults to the value of `--format` (so `--format json` flips both, as before the split). `fmt` and `lint` pass through native `plxt` output.

It is consumed by the `mthds-agent` CLI (from the `mthds` npm package) which itself is used by Claude Code skills, the VS Code extension, and can be called directly from the command line.

## Global Options

| Option | Description |
|--------|-------------|
| `--runner` | Select the runner backend to use (`pipelex` or `api`) |
| `--version` | Print the version and exit |

There is no `--log-level` flag: `pipelex-agent` is machine-consumed, so logging is cut off process-wide by design.

## Commands Overview

The agent CLI mirrors the main CLI's subcommand structure for `run`, `validate`, and `inputs`, each with `pipe`, `bundle`, and `method` subcommands. It also provides `fix bundle` for deterministic in-place repairs.

### Run

Execute a pipeline. Success output is markdown by default, or JSON with `--format json`. Errors follow `--error-format` (defaults to `--format`'s value).

```bash
pipelex-agent run pipe <PIPE_CODE> [OPTIONS]
pipelex-agent run bundle <PATH> [OPTIONS]
pipelex-agent run method <NAME> [OPTIONS]
```

**Common options:**

- `--inputs`, `-i` - Path to a JSON or TOML inputs file (discriminated by file extension: `.toml` → TOML, everything else → JSON). Inline JSON (a value starting with `{`) stays JSON-only.
- `--dry-run` - Dry-run without calling AI providers
- `--mock-inputs` - Use mock inputs (requires `--dry-run`)
- `--graph` / `--no-graph` - Enable/disable execution graph (enabled by default)
- `--library-dir`, `-L` - Additional library directory
- `--with-memory` - Include full working memory in output
- `--format` - Success output format: `markdown` (default) or `json`
- `--error-format` - Error output format: `markdown` or `json` (defaults to `--format`'s value)

For `bundle` and `method`, use `--pipe` to target a specific pipe.

!!! note "Stdin inputs stay JSON"
    The agent CLI can also read inputs from stdin (a flat dict or a `working_memory` envelope). Stdin inputs are **JSON-only** — the extension-based TOML discrimination applies to `--inputs` file paths only. Like the main CLI, `run bundle <dir>` auto-detects `inputs.json` / `inputs.toml` when `--inputs` is omitted, erroring if both exist.

### Validate

Validate pipes, bundles, or methods. Success output is markdown by default, or JSON with `--format json`. Errors follow `--error-format` (defaults to `--format`'s value).

```bash
pipelex-agent validate pipe <PIPE_CODE> [OPTIONS]
pipelex-agent validate pipe --all [OPTIONS]
pipelex-agent validate bundle <PATH> [OPTIONS]
pipelex-agent validate method <NAME> [OPTIONS]
```

**Common options:**

- `--library-dir`, `-L` - Additional library directory
- `--allow-signatures` - Accept [`PipeSignature`](../../building-methods/pipes/signature-pipes.md) placeholders in the dependency graph (lenient mode)
- `--format` - Success output format: `markdown` (default) or `json`
- `--error-format` - Error output format: `markdown` or `json` (defaults to `--format`'s value)

For `bundle`, additional options are available:

- `--pipe` - Require a specific pipe in the bundle
- `--graph`, `-g` - Generate an execution graph visualization
- `--graph-format`, `-f` - Graph output format (`mermaidflow`, `reactflow`, or `both`)
- `--direction` - Graph layout direction

!!! note "Signature pipes"
    `pipelex-agent validate` is strict by default — same as `pipelex validate`. A bundle whose dependency graph reaches a `PipeSignature` is rejected unless you pass `--allow-signatures`, which dry-runs signatures as mocks.

    On a successful run, the envelope also carries `pending_signatures` — the library-wide list of pipes still declared as `PipeSignature` (unimplemented forward declarations), each namespaced by `pipe_ref` (`domain.code`). In JSON it is a `pending_signatures` array, in markdown a "Pending signatures" section. A top-down build reads it to see exactly which headers remain to implement. The envelope also carries a derived `is_runnable` boolean (`true` ⇔ `pending_signatures` is empty), and the markdown states the runnability verdict in plain English — runnable when complete, NOT yet runnable above the "Pending signatures" section otherwise. `validate bundle`, `validate method`, and `validate pipe --all` carry them and gate on them: without `--allow-signatures`, the command exits non-zero when `is_runnable` is false. Bare `validate pipe <code>` omits them, and a `--pipe` slice surfaces them for information without gating.

!!! note "Advisory warnings on validate"
    Whole-bundle and whole-library validate surfaces (`validate bundle`, `validate method`, `validate pipe --all`) also carry a `warnings` array — advisory optionality lints on a VALID bundle that never flip the verdict or the exit code. Each entry has the **same shape as a validation error item** (`category`, `error_type`, `pipe_code`, `domain_code`, `variable_names`, `message`) — this is a different shape from the `init`/`doctor` setup `warnings` (`{type, message}`) documented under Output Contract below. The first occupant is the useless-`!` lint (`optional_force_redundant`): a `!` (force) input whose slot is guaranteed present in every analyzed flow, so the assertion can never fire. In markdown, warnings render as a "Warnings" section. The array is empty when there is nothing to report; single-pipe `validate pipe` omits it (no flow context to lint in).

### Fix

Apply deterministic safe fixes to a bundle, re-validating after each round until the bundle is valid, no applicable fix remains, or the iteration limit is reached.

```bash
pipelex-agent fix bundle <PATH> [OPTIONS]
```

**Options:**

- `--library-dir`, `-L` - Additional library directory; files in explicitly supplied directories may be fixed when an error identifies them as the source
- `--allow-signatures` - Accept `PipeSignature` placeholders during validation
- `--max-iterations` - Limit the number of validate/apply rounds
- `--select` - Apply only the named fix rule; repeat for multiple rules
- `--ignore` - Skip the named fix rule; repeat for multiple rules (`--select` and `--ignore` are mutually exclusive)
- `--format` - Success output format: `markdown` (default) or `json`
- `--error-format` - Error output format: `markdown` or `json` (defaults to `--format`'s value)

The result reports `iterations`, `fixes_applied`, `files_written`, and any `remaining_errors`. A fully valid result exits 0; a completed fix attempt that remains invalid exits 1; argument, setup, or unexpected failures exit 2.

### Inputs

Generate an example inputs template for a pipe, bundle, or method. By default the template is the **light** signature-driven shape (bare values matching the pipe's declared concepts), which is exactly what `run` accepts; `--explicit` emits the ceremonial `{concept, content}` envelope form instead.

```bash
pipelex-agent inputs pipe <PIPE_CODE> [OPTIONS]
pipelex-agent inputs bundle <PATH> [OPTIONS]
pipelex-agent inputs method <NAME> [OPTIONS]
```

**Common options:**

- `--library-dir`, `-L` - Additional library directory
- `--format` - Template serialization: `json` (default) or `toml`
- `--explicit` - Emit the ceremonial `{concept, content}` envelope form instead of the light values

For `bundle` and `method`, use `--pipe` to target a specific pipe.

!!! note "`inputs --format` is `json|toml`, not `markdown|json`"
    Unlike `run`/`validate`, the `inputs` command's `--format` selects the **template serialization**, not a presentation style. `json` (the default) emits the structured JSON success envelope; `toml` prints the raw TOML template straight to stdout (a pipe with no inputs prints a TOML comment line, which loads back as an empty dict). This mirrors the raw-TOML output of the `concept` and `pipe` commands. `inputs` has no `--error-format` — its errors stay JSON.

!!! note "`--explicit` and concept hints"
    The light `--format toml` template carries the declared concept for each key as a `# concept: ...` comment; the light `--format json` template (the default) cannot (JSON has no comments), so pass `--explicit` when you want the concept written out inline. The JSON success envelope shape (`success` / `pipe_code` / `inputs`) is unchanged — only the `inputs` payload flips between the light values and the envelope form.

### Flat Commands

These commands do not have subcommands:

| Command | Description |
|---------|-------------|
| `fmt` | Format a `.mthds`/`.toml`/`.plx` file in-place (delegates to `plxt`) |
| `lint` | Lint a `.mthds`/`.toml`/`.plx` file for errors (delegates to `plxt`) |
| `concept` | Convert a JSON concept spec into raw TOML (stdout) |
| `pipe` | Convert a JSON pipe spec into raw TOML (stdout) |
| `models` | List available model presets, aliases, and waterfalls (`--format markdown\|json` success, default: markdown; `--error-format` for errors, defaults to `--format`'s value) |
| `doctor` | Check config, credentials, and model health (`--format markdown\|json` success, default: markdown; `--error-format` for errors, defaults to `--format`'s value) |

## Output Contract

Commands use different stdout formats depending on their purpose:

- **Markdown or JSON**: `run`, `validate`, `fix`, `init`, `models`, `check-model`, `doctor` — markdown by default, JSON with `--format json`. Error format follows `--error-format` (defaults to `--format`'s value, so `--format json` flips both).
- **JSON or raw TOML**: `inputs` — structured JSON via `agent_success()` by default (`--format json`), or the raw TOML template printed directly to stdout with `--format toml`
- **Raw TOML**: `concept`, `pipe` — TOML text printed directly to stdout
- **Passthrough**: `fmt`, `lint` — raw `plxt` output

**JSON success** — written to stdout:

```json
{
  "success": true,
  "target_dir": "/path/to/.pipelex",
  "backends_enabled": ["openai"]
}
```

JSON commands return the result object directly. They are not wrapped in a `status` or `data` envelope.

**Warnings** — non-fatal setup conditions are surfaced on a top-level `warnings` array of the success envelope, so consumers don't have to parse stderr. The field is absent when there is nothing to report. Each entry is an object with a `type` and a `message`:

```json
{
  "success": true,
  "target_dir": "/path/to/.pipelex",
  "warnings": [
    { "type": "RemoteConfigStale", "message": "Using a cached gateway config; run `pipelex init` while online to refresh." }
  ]
}
```

`RemoteConfigStale` is emitted when the gateway is enabled but the remote config service is unreachable and Pipelex falls back to its on-disk cache (offline mode).

Do not confuse this setup-warning shape with the `warnings` array on the `validate` envelope — validate warnings are advisory lint items that reuse the validation-error item shape (see "Advisory warnings on validate" above).

**Error** — written to stderr:

```json
{
  "error": true,
  "error_type": "specific_error_type",
  "message": "Human-readable description",
  "error_domain": "input",
  "hint": "Suggested fix or next step",
  "retryable": false
}
```

Exactly one such object is written to stderr per failure, so the stream parses as a single JSON document.

**`migration`** — a configuration error (`"error_domain": "config"`) carries an extra `migration` object when, and only when, a scan of this machine's configuration directories found something. Its presence is the whole signal: the configuration is *out of date* rather than wrong. It holds `remedy` (the command that fixes what can be fixed), `needs_attention` (whether something there is a person's decision rather than the tool's), and `plans` — one per file, in the same shape [`pipelex-agent migrate`](migrate.md) emits under its own `plans` key. The loop from there is `pipelex-agent migrate --dry-run --format json`, show the user what would change, then `--yes`. Never hand-edit a configuration file, and never answer this by re-initializing one — that discards every setting the migration would have kept.

    `TelemetryConfigValidationError` carries it too, on the same terms: present means the `telemetry.toml` is old, absent means it is wrong and the fields the message names are what to correct.

    **A failure is not the only way to learn this, and for an agent it is not even the reliable one.** A configuration the migration history explains boots with a warning rather than an error — and `pipelex-agent` silences logging process-wide before anything can emit one, so no error arrives and the machine is still stale. `pipelex-agent doctor` is the channel that always answers: its `checks.pending_migrations` row carries a `finding` (`up_to_date`, `pending`, `needs_attention`, `unavailable`), the `migratable_files` a migration would rewrite, and the `attention_files` it will not repair on its own. Branch on `finding`; `unavailable` means the check could not run and is not a claim that the machine is current. The row answers for both configuration directories even under `--global`, because it describes `pipelex migrate`, which has no such flag.

`fmt` and `lint` are raw passthroughs to the `plxt` binary and bypass the JSON output contract, producing native `plxt` output instead.

## Graph Visualization

Graph visualization is available through the `validate bundle` subcommand with the `--graph` flag, and through `run` subcommands where it is enabled by default. Use `--no-graph` on `run` to disable it.
