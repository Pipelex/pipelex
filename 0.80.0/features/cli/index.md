# Command-Line Interface

A comprehensive CLI for developing, validating, and running AI methods.

## Overview

The `pipelex` CLI is the primary tool for working with Pipelex methods. It covers the full development lifecycle: initialization, building, validation, execution, inspection, and diagnostics.

## Core Commands

| Command | Description |
|---------|-------------|
| **`pipelex init`** | Initialize configuration, choose where runs execute (the hosted Pipelex API or this machine), and set up backends, credentials, routing, and telemetry |
| **`pipelex login`** | Get a Pipelex API key through your browser, or paste one with `--paste`, and save it for runs on the hosted Pipelex API |
| **`pipelex update`** | Refresh the model deck and `backends/internal.toml` to match the installed pipelex version |
| **`pipelex migrate`** | Bring your configuration files up to the schema the installed version expects, and clean up what a former release left |
| **`pipelex doctor`** | Check configuration health and suggest fixes; a setup whose runs execute on the hosted Pipelex API needs its Pipelex API key and no provider key |
| **`pipelex build`** | Generate the structures of your concepts and example inputs and outputs for a pipe |
| **`pipelex validate`** | Check pipeline syntax, structure, and run dry-run validation |
| **`pipelex fix`** | Apply deterministic safe fixes to a bundle and re-validate (with `--diff` preview) |
| **`pipelex run`** | Execute pipelines from bundle files, libraries or methods, on this machine or on the hosted Pipelex API |
| **`pipelex graph`** | Generate and render execution graphs |
| **`pipelex show`** | Display configuration, pipes, and list AI models |
| **`pipelex which`** | Locate where a pipe is defined, similar to `which` for executables |

## Related CLI

Package manifest management is currently exposed through the lowercase `mthds` CLI:

- `mthds package init`
- `mthds package list`
- `mthds package validate`

## Execution Options

- **Where it runs** — `--hosted` runs on the hosted Pipelex API, with only a Pipelex API key, and `--local` on this machine, with your own provider keys; without either, the run follows `[run] execution`. `--base-url` points a hosted run at another origin. See [Running on the Hosted API](../tools/cli/run.md#running-on-the-hosted-api)
- **Dry run** — `--dry-run` executes with mocked LLM responses to test pipeline logic without API calls
- **Mock inputs** — `--mock-inputs` generates synthetic inputs so you can test a pipeline without preparing real data (requires `--dry-run`)
- **Graph generation** — `--graph`, `--graph-full-data`, `--graph-no-data` for visual execution inspection

## Agent CLI

The `pipelex-agent` CLI is a machine-first interface designed for automated environments like Claude Code skills. Output format varies by command — markdown or JSON, raw TOML, or `plxt` passthrough — with no interactive prompts or Rich formatting. Structured commands emit errors to stderr; the error format is controlled by `--error-format` and defaults to the value of `--format` (so `--format json` flips both). `fmt` and `lint` pass through native `plxt` output.

| Command | Description |
|---------|-------------|
| `init` | Non-interactive configuration setup; `"execution": "hosted"` in `--config` sets up hosted runs (`--format markdown\|json` success, default: markdown; `--error-format` for errors, defaults to `--format`'s value) |
| `run` | Execute a pipeline (`--format markdown\|json` success, default: markdown; `--error-format` for errors, defaults to `--format`'s value) |
| `validate` | Validate pipes, bundles, or methods (`--format markdown\|json` success, default: markdown; `--error-format` for errors, defaults to `--format`'s value) |
| `fix` | Apply deterministic safe fixes to a bundle in place and re-validate (`--format markdown\|json` success, default: markdown; `--error-format` for errors, defaults to `--format`'s value) |
| `fmt` | Format `.mthds`, `.toml`, or `.plx` files in-place |
| `lint` | Lint files for errors |
| `inputs` | Generate example input JSON for a pipe |
| `models` | List available model presets, aliases, and waterfalls (`--format markdown\|json` success, default: markdown; `--error-format` for errors, defaults to `--format`'s value) |
| `doctor` | Check configuration health (`--format markdown\|json` success, default: markdown; `--error-format` for errors, defaults to `--format`'s value) |

For detailed CLI documentation, see the [CLI reference](../tools/cli/index.md).

## Related Documentation

- [CLI Reference](../tools/cli/index.md) - Runtime CLI commands
- [Agent CLI](../tools/cli/agent-cli.md) - Machine-oriented interface for AI agents
- [Package Commands](../tools/cli/pkg.md) - Current `mthds package` manifest commands
