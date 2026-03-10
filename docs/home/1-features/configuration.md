---
title: Configuration System
---

# Configuration System

Multi-level TOML configuration for full control over Pipelex behavior.

## Overview

<!-- TODO: Expand with configuration philosophy -->

Pipelex uses a layered TOML configuration system that lets you define sensible defaults and override them at any level: project, environment, or run mode.

## Configuration Levels

<!-- TODO: Describe each level with examples -->

1. **Base defaults** — Built into Pipelex (`pipelex.toml` in the package)
2. **Project overrides** — `.pipelex/pipelex.toml` in your project root
3. **Environment-specific** — `pipelex_dev.toml`, `pipelex_prod.toml`, etc.
4. **Local overrides** — `pipelex_local.toml` (git-ignored)
5. **Run-mode-specific** — Overrides for specific execution contexts

## Environment Variables

<!-- TODO: Describe ${VAR_NAME} syntax -->

Use `${VAR_NAME}` syntax in TOML files for dynamic configuration from environment variables.

## Key Configuration Areas

<!-- TODO: Brief overview linking to detailed docs -->

- **[Inference Backends](../7-configuration/config-technical/inference-backend-config.md)** — LLM providers, models, and routing
- **[Logging](../7-configuration/config-practical/logging-config.md)** — Log levels and output
- **[Telemetry](../7-configuration/config-practical/telemetry-config.md)** — Observability settings
- **[Reporting](../7-configuration/config-practical/reporting-config.md)** — Cost tracking and reports
- **[Dry Run](../7-configuration/config-pipeline-validation/dry-run-config.md)** — Mock generation settings
- **[Features](../7-configuration/config-advanced/feature-config.md)** — Feature flags

For full configuration reference, see [Configuration](../7-configuration/index.md).
