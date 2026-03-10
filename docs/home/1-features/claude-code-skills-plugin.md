---
title: Claude Code Skills Plugin
---

# Claude Code Skills Plugin

Build, run, validate, and edit AI methods directly from Claude Code.

## Overview

The **MTHDS skills plugin** for Claude Code brings the full Pipelex workflow into your AI coding assistant. Build methods from natural language, validate them, run them, and iterate — all through conversational slash commands. The plugin leverages the `pipelex-agent` CLI under the hood for structured JSON communication.

Install from [mthds-ai/skills](https://github.com/mthds-ai/skills).

## Available Commands

| Command | Description |
|---------|-------------|
| `/mthds-build` | Build new AI method bundles from scratch |
| `/mthds-check` | Validate workflow bundles for issues (read-only) |
| `/mthds-edit` | Modify existing bundles — change pipes, update prompts, add or remove steps |
| `/mthds-explain` | Explain and document existing workflows in plain language |
| `/mthds-fix` | Automatically fix validation errors in a loop |
| `/mthds-run` | Execute methods and interpret JSON output (supports dry runs and graph generation) |
| `/mthds-inputs` | Prepare inputs: placeholder templates, synthetic test data, or user-provided files |
| `/mthds-install` | Install method packages from GitHub or local directories |
| `/mthds-pkg` | Manage packages — initialize, add dependencies, lock, install, update, validate |
| `/mthds-publish` | Publish methods to mthds.sh |

## Getting Started

```text
# Run these inside Claude Code:
/plugin marketplace add mthds-ai/skills
/plugin install mthds@mthds-ai-skills
```

Once installed, type `/mthds-build` in Claude Code to create your first method from a natural language description.
