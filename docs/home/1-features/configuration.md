---
title: Configuration System
---

# Configuration System

Multi-level TOML configuration for full control over Pipelex behavior.

## Overview

Pipelex uses a layered TOML configuration system that lets you define sensible defaults and override them at any level: project, environment, or run mode. Each layer merges on top of the previous one, so you only need to specify what you want to change.

## Configuration Levels

1. **Base defaults** — Built into Pipelex (`pipelex.toml` in the package)
2. **Global overrides** — `~/.pipelex/pipelex.toml` for user-wide settings
3. **Project overrides** — `{project_root}/.pipelex/pipelex.toml` for project-specific settings
4. **Local overrides** — `pipelex_local.toml` (git-ignored) for machine-specific values
5. **Environment / run-mode-specific** — `pipelex_dev.toml`, `pipelex_prod.toml`, `pipelex_testing.toml`, etc.

A final `pipelex_override.toml` file can be used for last-resort overrides.

## Environment Variables

Use `${VAR_NAME}` syntax in TOML files for dynamic configuration from environment variables and secrets. Supports `${env:VAR}` for environment variables, `${secret:VAR}` for the secrets provider, and fallback chains like `${env:VAR|secret:VAR}`.

## Key Configuration Areas

- **[Inference Backends](../7-configuration/config-technical/inference-backend-config.md)** — LLM providers, models, and routing
- **[Logging](../7-configuration/config-practical/logging-config.md)** — Log levels and output
- **[Telemetry](../7-configuration/config-practical/telemetry-config.md)** — Observability settings
- **[Reporting](../7-configuration/config-practical/reporting-config.md)** — Cost tracking and reports
- **[Dry Run](../7-configuration/config-pipeline-validation/dry-run-config.md)** — Mock generation settings
- **[Features](../7-configuration/config-advanced/feature-config.md)** — Feature flags

For full configuration reference, see [Configuration](../7-configuration/index.md).
