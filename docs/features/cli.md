---
title: "CLI"
description: "The Pipelex command-line interface for developing, validating, and running AI methods. Covers login, init, build, validate, run, graph, show, and more."
---

# Command-Line Interface

A comprehensive CLI for developing, validating, and running AI methods.

## Overview

The `pipelex` CLI is the primary tool for working with Pipelex methods. It covers the full development lifecycle: authentication, initialization, building, validation, execution, inspection, and diagnostics.

## Core Commands

| Command | Description |
|---------|-------------|
| **`pipelex login`** | Authenticate with Pipelex Gateway via the browser and save your API key |
| **`pipelex init`** | Initialize configuration, backends, credentials, routing, and telemetry |
| **`pipelex update`** | Refresh the model deck to match the installed pipelex version |
| **`pipelex doctor`** | Check configuration health and suggest fixes |
| **`pipelex build`** | AI-powered method generation from natural language requirements |
| **`pipelex validate`** | Check pipeline syntax, structure, and run dry-run validation |
| **`pipelex run`** | Execute pipelines from bundle files or libraries |
| **`pipelex graph`** | Generate and render execution graphs |
| **`pipelex show`** | Display configuration, pipes, and list AI models |
| **`pipelex which`** | Locate where a pipe is defined, similar to `which` for executables |

## Related CLI

Package manifest management is currently exposed through the lowercase `mthds` CLI:

- `mthds package init`
- `mthds package list`
- `mthds package validate`

## Execution Options

- **Dry run** — `--dry-run` executes with mocked LLM responses to test pipeline logic without API calls
- **Mock inputs** — `--mock-inputs` generates synthetic inputs so you can test a pipeline without preparing real data
- **Graph generation** — `--graph`, `--graph-full-data`, `--graph-no-data` for visual execution inspection

## Agent CLI

The `pipelex-agent` CLI is a machine-first interface designed for automated environments like Claude Code skills. Output format varies by command — markdown or JSON, raw TOML, or `plxt` passthrough — with no interactive prompts or Rich formatting. Structured commands emit errors to stderr; the error format is controlled by `--error-format` and defaults to the value of `--format` (so `--format json` flips both). `fmt` and `lint` pass through native `plxt` output.

| Command | Description |
|---------|-------------|
| `init` | Non-interactive configuration setup (`--format markdown\|json` success, default: markdown; `--error-format` for errors, defaults to `--format`'s value) |
| `run` | Execute a pipeline (`--format markdown\|json` success, default: markdown; `--error-format` for errors, defaults to `--format`'s value) |
| `validate` | Validate pipes, bundles, or methods (`--format markdown\|json` success, default: markdown; `--error-format` for errors, defaults to `--format`'s value) |
| `fmt` | Format `.mthds`, `.toml`, or `.plx` files in-place |
| `lint` | Lint files for errors |
| `inputs` | Generate example input JSON for a pipe |
| `concept` | Convert a JSON concept spec into raw TOML (stdout) |
| `pipe` | Convert a JSON pipe spec into raw TOML (stdout) |
| `models` | List available model presets, aliases, and waterfalls (`--format markdown\|json` success, default: markdown; `--error-format` for errors, defaults to `--format`'s value) |
| `doctor` | Check configuration health (`--format markdown\|json` success, default: markdown; `--error-format` for errors, defaults to `--format`'s value) |

For detailed CLI documentation, see the [CLI reference](../tools/cli/index.md).

## Related Documentation

- [CLI Reference](../tools/cli/index.md) - Runtime CLI commands
- [Agent CLI](../tools/cli/agent-cli.md) - Machine-oriented interface for AI agents
- [Package Commands](../tools/cli/pkg.md) - Current `mthds package` manifest commands
