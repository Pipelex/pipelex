---
description: "Use the pipelex-agent CLI for machine-oriented output — designed for AI agents, IDE extensions, and automation toolchains."
---

# Agent CLI (`pipelex-agent`)

The `pipelex-agent` CLI is a machine-oriented companion to the main `pipelex` CLI. It is designed for programmatic consumption by AI agents, IDE extensions, and other automation tools. Output format varies by command — markdown or JSON, raw TOML, or `plxt` passthrough — with no Rich formatting or interactive prompts. Structured commands emit errors to stderr; the error format is controlled by `--error-format`, which defaults to the value of `--format` (so `--format json` flips both, as before the split). `fmt` and `lint` pass through native `plxt` output.

It is consumed by the `mthds-agent` CLI (from the `mthds` npm package) which itself is used by Claude Code skills, the VS Code extension, and can be called directly from the command line.

## Global Options

| Option | Description |
|--------|-------------|
| `--log-level` | Set the logging level (e.g., `debug`, `info`, `warning`, `error`) |
| `--runner` | Select the runner backend to use |
| `--version` | Print the version and exit |

## Commands Overview

The agent CLI mirrors the main CLI's subcommand structure for `run`, `validate`, and `inputs`, each with `pipe`, `bundle`, and `method` subcommands.

### Run

Execute a pipeline. Success output is markdown by default, or JSON with `--format json`. Errors follow `--error-format` (defaults to `--format`'s value).

```bash
pipelex-agent run pipe <PIPE_CODE> [OPTIONS]
pipelex-agent run bundle <PATH> [OPTIONS]
pipelex-agent run method <NAME> [OPTIONS]
```

**Common options:**

- `--inputs`, `-i` - Path to JSON input file
- `--dry-run` - Dry-run without calling AI providers
- `--mock-inputs` - Use mock inputs
- `--graph` / `--no-graph` - Enable/disable execution graph (enabled by default)
- `--library-dir`, `-L` - Additional library directory
- `--with-memory` - Include full working memory in output
- `--format` - Success output format: `markdown` (default) or `json`
- `--error-format` - Error output format: `markdown` or `json` (defaults to `--format`'s value)

For `bundle` and `method`, use `--pipe` to target a specific pipe.

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

### Inputs

Generate example input JSON for a pipe, bundle, or method.

```bash
pipelex-agent inputs pipe <PIPE_CODE> [OPTIONS]
pipelex-agent inputs bundle <PATH> [OPTIONS]
pipelex-agent inputs method <NAME> [OPTIONS]
```

**Common options:**

- `--library-dir`, `-L` - Additional library directory

For `bundle` and `method`, use `--pipe` to target a specific pipe.

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

- **Markdown or JSON**: `run`, `validate`, `init`, `models`, `check-model`, `doctor` — markdown by default, JSON with `--format json`. Error format follows `--error-format` (defaults to `--format`'s value, so `--format json` flips both).
- **JSON**: `inputs` — structured JSON via `agent_success()`
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

`fmt` and `lint` are raw passthroughs to the `plxt` binary and bypass the JSON output contract, producing native `plxt` output instead.

## Graph Visualization

Graph visualization is available through the `validate bundle` subcommand with the `--graph` flag, and through `run` subcommands where it is enabled by default. Use `--no-graph` on `run` to disable it.
