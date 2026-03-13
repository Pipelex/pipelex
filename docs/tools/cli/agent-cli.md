---
description: "Use the pipelex-agent CLI for machine-oriented JSON output — designed for AI agents, IDE extensions, and automation toolchains."
---

# Agent CLI (`pipelex-agent`)

The `pipelex-agent` CLI is a machine-oriented companion to the main `pipelex` CLI. It is designed for programmatic consumption by AI agents, IDE extensions, and other automation tools. All output is structured JSON written to stdout (success) or stderr (error), with no Rich formatting or interactive prompts.

Its structured JSON output makes it well-suited for piping into other tools (e.g., `jq`), scripting, and integration into larger workflows. It is consumed by the `mthds-agent` CLI (from the `mthds` npm package) which itself is used by Claude Code skills, the VS Code extension, and can be called directly from the command line.

## Global Options

| Option | Description |
|--------|-------------|
| `--log-level` | Set the logging level (e.g., `debug`, `info`, `warning`, `error`) |
| `--runner` | Select the runner backend to use |
| `--version` | Print the version and exit |

## Commands Overview

The agent CLI mirrors the main CLI's subcommand structure for `run`, `validate`, and `inputs`, each with `pipe`, `bundle`, and `method` subcommands.

### Run

Execute a pipeline and return results as JSON.

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

For `bundle` and `method`, use `--pipe` to target a specific pipe.

### Validate

Validate pipes, bundles, or methods and return status as JSON.

```bash
pipelex-agent validate pipe <PIPE_CODE> [OPTIONS]
pipelex-agent validate pipe --all [OPTIONS]
pipelex-agent validate bundle <PATH> [OPTIONS]
pipelex-agent validate method <NAME> [OPTIONS]
```

**Common options:**

- `--library-dir`, `-L` - Additional library directory

For `bundle`, additional options are available:

- `--pipe` - Require a specific pipe in the bundle
- `--graph`, `-g` - Generate an execution graph visualization
- `--format`, `-f` - Graph output format
- `--direction` - Graph layout direction

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
| `concept` | Convert a JSON concept spec into TOML |
| `pipe` | Convert a JSON pipe spec into TOML |
| `assemble` | Merge concept and pipe TOML sections into a complete `.mthds` file |
| `models` | List available model presets, aliases, waterfalls, and talent mappings |
| `doctor` | Check config, credentials, and model health |

## Output Contract

Every command (except `fmt` and `lint`) returns structured JSON via one of two functions:

**Success** — written to stdout:

```json
{
  "status": "success",
  "data": { ... }
}
```

**Error** — written to stderr:

```json
{
  "status": "error",
  "error_type": "specific_error_type",
  "message": "Human-readable description",
  "domain": "input | config | runtime",
  "hint": "Suggested fix or next step",
  "retryable": false
}
```

`fmt` and `lint` are raw passthroughs to the `plxt` binary and bypass the JSON output contract, producing native `plxt` output instead.

## Graph Visualization

Graph visualization is available through the `validate bundle` subcommand with the `--graph` flag, and through `run` subcommands where it is enabled by default. Use `--no-graph` on `run` to disable it.
