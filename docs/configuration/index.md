---
description: "Configure Pipelex with its layered TOML configuration system — shipped defaults plus project-level overrides for executable AI methods."
---

# Configuration

## Overview

Pipelex uses a TOML-based configuration system with **shipped defaults** plus **project-level overrides**.

- **Shipped defaults**: Pipelex ships default values that are maintained in the Pipelex repository (contributors will see them in the repo root `pipelex.toml`). This is the baseline used by the installed package.
- **Project overrides**: a project that *uses* Pipelex typically customizes behavior via files created in `.pipelex/`.

You can create the configuration files by running:

```bash
pipelex init config          # creates the global config at ~/.pipelex/
pipelex init config --local  # creates the project config at {project_root}/.pipelex/
```

!!! important "Configuration Setup Notes"
    1. By default `pipelex init config` targets the **global** `~/.pipelex/` directory; pass `--local` to create the project-level `.pipelex/` instead.
    2. `pipelex init config` creates a **template** configuration file with sample settings. It does not include all possible configuration options - it's meant as a starting point.
    3. Running `pipelex init config` will **overwrite** your existing `pipelex.toml` file without warning. Make sure to backup your configuration before running this command.
    4. Credentials (`~/.pipelex/.env`) and the Gateway service-agreement file always remain in the global `~/.pipelex/` directory regardless of `--local` — only config, inference, and telemetry files are written to the project `.pipelex/`.

For a complete list of all possible configuration options, refer to the configuration group documentation below.

## Where to edit configuration in a project

The main project configuration files are:

- `.pipelex/pipelex.toml`: project customization (logging, reporting, feature flags, etc.)
- `.pipelex/telemetry.toml`: custom telemetry destinations
- `.pipelex/inference/…`: inference backends, routing profiles, and model presets

## Overrides (advanced)

In addition to the base `pipelex.toml`, Pipelex applies override files from **inside** each `.pipelex/` directory (both the global `~/.pipelex/` and the project's `.pipelex/`) for machine- and environment-specific settings:

1. `pipelex_local.toml`
2. `pipelex_{environment}.toml` (example: `pipelex_dev.toml`) — selected by the `PIPELEX_ENV` environment variable (see [Selecting the environment](#selecting-the-environment))
3. `pipelex_{run_mode}.toml` (example: `pipelex_normal.toml`; unit tests use `tests/pipelex_unit_test.toml`, the one override file read outside a `.pipelex/` directory)
4. `pipelex_override.toml` (recommended to gitignore)
5. `pipelex_temporary_override.toml` (recommended to gitignore)

!!! info "Contributor details"
    For the full “where defaults live” and “how config is merged” explanation, see [Configuration Internals](../contribute/configuration-defaults-and-overrides.md).

## Configuration Structure

The configuration is organized into four main sections, which mirror the layers of the runtime:

1. `[runtime]` - process-scoped infrastructure: storage, secrets, logging, cloud credentials, reporting, tracing, observation, and the plugin denylist
2. `[inference]` - the model-calling seam: the model deck, LLM, image generation, extraction, the default templating style, and dry-run mocks
3. `[interpreter]` - library-scoped method machinery: MTHDS parsing, pipe runs, pipe functions, pipeline execution, source scanning, and the builder
4. `[kit]` - settings for the `pipelex-dev` kit tooling

Each section contains multiple subsections for specific features and functionalities. A setting's address tells you which layer owns it: `[runtime.*]` applies to any process, whatever it loads; `[interpreter.*]` only means something once a method is loaded.

!!! tip "If your file predates this layout"
    A `pipelex.toml` written against an older layout still boots. Pipelex carries it forward in memory, warns you that it did, and changes nothing on disk; `pipelex doctor` reports the pending migration. `pipelex migrate` is what makes it permanent — it rewrites each file in place and keeps the original beside it as a timestamped `.bak`. Your settings move address, they do not change value. The command walks the global `~/.pipelex/` and your project's `.pipelex/`, so a file you load from somewhere else — through `Pipelex.make(config_dir=…)` — is yours to update where it lives, and the boot warning says so rather than naming a command that would not reach it. Your inference backend definitions under `inference/backends/` are migratable the same way; the [inference backend page](config-technical/inference-backend-config.md) says what a migration will and will not touch in one. See [Migration Ledger](../migration-ledger.md) for what a migration may and may not do to your file.

## Configuration Override System

Pipelex uses a sophisticated configuration override system that loads and merges configurations in a specific order. This allows for fine-grained control over settings in different environments and scenarios.

The exact loading sequence is (later wins, per leaf key):

1. Base configuration from the installed Pipelex package (`pipelex.toml`)
2. Global base configuration (`~/.pipelex/pipelex.toml`)
3. Global override sequence, from `~/.pipelex/`: `pipelex_local.toml`, `pipelex_{environment}.toml`, `pipelex_{run_mode}.toml`, `pipelex_override.toml`, `pipelex_temporary_override.toml`
4. Your project's base configuration (`{project_root}/.pipelex/pipelex.toml`)
5. Project override sequence, from the project's `.pipelex/`: the same five files as step 3
6. Programmatic overrides passed in code, if any

Notes on the override sequence:

- `pipelex_{environment}.toml` (example: `pipelex_dev.toml`) is selected by the `PIPELEX_ENV` environment variable (see [Selecting the environment](#selecting-the-environment))
- `pipelex_{run_mode}.toml` — example run modes: normal, unit_test; under unit testing the run-mode overlay is sourced exclusively from `./tests/pipelex_{run_mode}.toml`
- Each subsequent configuration file in this sequence can override settings from the previous ones, and project-level files override the global `~/.pipelex/` layer

### Override File Naming

- Base config: `pipelex.toml`
- Local overrides: `pipelex_local.toml`
- Environment overrides: `pipelex_dev.toml`, `pipelex_staging.toml`, `pipelex_prod.toml`, etc.
- Run mode overrides: `pipelex_normal.toml`, `tests/pipelex_unit_test.toml`, etc.
- Final overrides: `pipelex_override.toml`

NB: The run_mode unit_test is used for testing purposes.

### Selecting the environment

The `pipelex_{environment}.toml` overlay is picked at runtime from the `PIPELEX_ENV` environment variable.

| Value     | Overlay file loaded   |
| --------- | --------------------- |
| `local`   | `pipelex_local.toml` *(also loaded as the local override layer; see above)* |
| `dev`     | `pipelex_dev.toml`     |
| `staging` | `pipelex_staging.toml` |
| `prod`    | `pipelex_prod.toml`    |

If `PIPELEX_ENV` is unset, Pipelex defaults to `dev`. Any other value raises an error at startup — the accepted values are defined by the `RunEnvironment` enum in `pipelex/system/runtime.py`.

The selected environment is also stamped on OpenTelemetry spans as `deployment.environment`, so it doubles as the environment label for traces and metrics.

Set it the way you set any other env var — for example, in your shell, your `.env` file, your CI configuration, or your container runtime:

```bash
export PIPELEX_ENV=staging
```

### Best Practices for Overrides

1. Use the base `pipelex.toml` for default settings
2. Use `pipelex_local.toml` for machine-specific settings
3. Use environment files for environment-specific settings (dev, staging, prod)
4. Use run mode files for normal or unit_test configurations
5. Use `pipelex_override.toml` sparingly, only for temporary overrides (add to .gitignore)

## Best Practices

1. **Version Control**: Include your base `pipelex.toml` in version control
2. **Environment Overrides**: Use environment-specific files for sensitive or environment-dependent settings
3. **Documentation**: Comment any custom settings for team reference
4. **Validation**: Run `pipelex validate --all` after making configuration changes
5. **Gitignore**: Add local and sensitive override files to `.gitignore`
