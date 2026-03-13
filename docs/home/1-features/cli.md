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
| **`pipelex doctor`** | Check configuration health and suggest fixes |
| **`pipelex build`** | AI-powered method generation from natural language requirements |
| **`pipelex validate`** | Check pipeline syntax, structure, and run dry-run validation |
| **`pipelex run`** | Execute pipelines from bundle files or libraries |
| **`pipelex graph`** | Generate and render execution graphs |
| **`pipelex show`** | Display configuration, pipes, and list AI models |
| **`pipelex which`** | Locate where a pipe is defined, similar to `which` for executables |

## Execution Options

- **Dry run** — `--dry-run` executes with mocked LLM responses to test pipeline logic without API calls
- **Mock inputs** — `--mock-inputs` generates synthetic inputs so you can test a pipeline without preparing real data
- **Graph generation** — `--graph`, `--graph-full-data`, `--graph-no-data` for visual execution inspection

## Agent CLI

The `pipelex-agent` CLI is a machine-first interface designed for automated environments like Claude Code skills. All output is structured JSON to stdout, with no interactive prompts or Rich formatting.

| Command | Description |
|---------|-------------|
| `init` | Non-interactive configuration setup |
| `run` | Execute a pipeline and output JSON results |
| `validate` | Validate pipes, bundles, or methods with JSON output |
| `fmt` | Format `.mthds`, `.toml`, or `.plx` files in-place |
| `lint` | Lint files for errors |
| `inputs` | Generate example input JSON for a pipe |
| `concept` | Convert a JSON concept spec into TOML |
| `pipe` | Convert a JSON pipe spec into TOML |
| `assemble` | Combine TOML parts into a complete `.mthds` file |
| `models` | List available model presets, aliases, and talent mappings |
| `doctor` | Check configuration health and auto-fix issues |

For detailed CLI documentation, see the [CLI reference](../9-tools/cli/index.md).
