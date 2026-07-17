# Configuration System

Multi-level TOML configuration for full control over Pipelex behavior.

## Overview

Pipelex uses a layered TOML configuration system that lets you define sensible defaults and override them at any level: project, environment, or run mode. Each layer merges on top of the previous one, so you only need to specify what you want to change.

## Configuration Levels

1. **Package defaults** — Built into Pipelex (`pipelex.toml` in the package)
2. **Global tier** — `~/.pipelex/` for user-wide settings: the base `pipelex.toml`, then its override sequence
3. **Project tier** — `{project_root}/.pipelex/` for project-specific settings: the base `pipelex.toml`, then the same override sequence

Within each tier, the base `pipelex.toml` is followed by an override sequence, merged in order (later wins per key):

- `pipelex_local.toml` — git-ignored, for machine-specific values
- `pipelex_{environment}.toml` — e.g. `pipelex_dev.toml`, `pipelex_prod.toml`. The environment is selected by the `PIPELEX_ENV` environment variable (accepted values: `local`, `dev`, `staging`, `prod`; defaults to `dev`).
- `pipelex_{run_mode}.toml` — e.g. `pipelex_unit_test.toml`, `pipelex_ci_test.toml`. The run mode is selected by the `RUN_MODE` environment variable (defaults to `normal`).
- `pipelex_override.toml` — general-purpose overrides
- `pipelex_temporary_override.toml` — last-resort, highest-precedence overrides within the tier

The entire global tier merges before the project tier, so any project-tier file — including the plain project `pipelex.toml` — overrides every global-tier file.

## Environment Variables

Two configuration areas support `${...}` variable substitution in their TOML files: the inference backend configuration (`.pipelex/inference/backends.toml` and the per-backend TOML files under `.pipelex/inference/backends/`) and the telemetry configuration (`.pipelex/telemetry.toml`). In those files, use `${env:VAR}` for environment variables, `${secret:VAR}` for the secrets provider, and fallback chains like `${env:VAR|secret:VAR}`. The `pipelex.toml` layering described above does not perform substitution — a `${env:VAR}` there stays a literal string.

## Key Configuration Areas

- **[Inference Backends](../configuration/config-technical/inference-backend-config.md)** — LLM providers, models, and routing
- **[Logging](../configuration/config-practical/logging-config.md)** — Log levels and output
- **[Telemetry](../configuration/config-practical/telemetry-config.md)** — Observability settings
- **[Reporting](../configuration/config-practical/reporting-config.md)** — Cost tracking and reports
- **[Dry Run](../configuration/config-pipeline-validation/dry-run-config.md)** — Mock generation settings

For full configuration reference, see [Configuration](../configuration/index.md).
