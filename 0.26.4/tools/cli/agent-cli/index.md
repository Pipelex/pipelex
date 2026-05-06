# Agent CLI (`pipelex-agent`)

The `pipelex-agent` CLI is a machine-oriented companion to the main `pipelex` CLI. It is designed for programmatic consumption by AI agents, IDE extensions, and other automation tools. Output format varies by command — JSON, raw TOML, or markdown — with no Rich formatting or interactive prompts. Structured commands emit JSON errors to stderr; `fmt` and `lint` pass through native `plxt` output.

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
| `concept` | Convert a JSON concept spec into raw TOML (stdout) |
| `pipe` | Convert a JSON pipe spec into raw TOML (stdout) |
| `models` | List available model presets, aliases, and waterfalls (`--format markdown\|json`, default: markdown) |
| `doctor` | Check config, credentials, and model health (`--format markdown\|json`, default: markdown) |

## Output Contract

Commands use different stdout formats depending on their purpose:

- **JSON**: `run`, `validate`, `inputs`, `init` — structured JSON via `agent_success()`
- **Raw TOML**: `concept`, `pipe` — TOML text printed directly to stdout
- **Markdown or JSON**: `models`, `doctor` — markdown by default, JSON with `--format json`
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
