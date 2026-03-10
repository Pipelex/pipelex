---
title: CLI
---

# Command-Line Interface

A comprehensive CLI for developing, validating, and running AI methods.

## Overview

<!-- TODO: Expand with CLI philosophy -->

The `pipelex` CLI is the primary tool for working with Pipelex methods. It covers the full development lifecycle: initialization, building, validation, execution, and inspection.

## Core Commands

<!-- TODO: Brief description of each, linking to detailed docs -->

| Command | Description |
|---------|-------------|
| **`pipelex init`** | Initialize a new project with configuration templates |
| **`pipelex run`** | Execute pipelines from bundle files or libraries |
| **`pipelex validate`** | Check pipeline syntax and structure without execution |
| **`pipelex show`** | Display pipeline structure and metadata |
| **`pipelex build`** | AI-powered pipeline generation (pipe, inputs, structures) |
| **`pipelex pkg`** | Package management commands |

## Execution Options

<!-- TODO: Describe key execution flags -->

- **Dry run** — `--dry-run` executes with mocked LLM responses
- **Mock inputs** — `--mock-inputs` generates synthetic inputs
- **Graph generation** — `--graph`, `--graph-full-data`, `--graph-no-data`

## Agent CLI

<!-- TODO: Describe agent-specific CLI operations -->

Agent-specific CLI operations for automated environments.

For detailed CLI documentation, see the [CLI reference](../9-tools/cli/index.md).
