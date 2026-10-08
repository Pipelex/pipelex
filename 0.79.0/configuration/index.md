# Configuration

## Overview

Pipelex uses a TOML-based configuration system with **shipped defaults** plus **project-level overrides**.

- **Shipped defaults**: Pipelex ships default values that are maintained in the Pipelex repository (contributors will see them in the repo root `pipelex.toml`). This is the baseline used by the installed package.
- **Project overrides**: a project that *uses* Pipelex typically customizes behavior via files created in `.pipelex/`.

You can create the configuration files by running:

```bash
pipelex init config          # creates the global config at ~/.pipelex/ (or in PIPELEX_HOME)
pipelex init config --local  # creates the project config at {project_root}/.pipelex/
```

!!! important "Configuration Setup Notes"
    1. By default `pipelex init config` targets the **global** `~/.pipelex/` directory, or the one `PIPELEX_HOME` names (see [below](#the-home-configuration-directory-pipelex_home)); pass `--local` to create the project-level `.pipelex/` instead.
    2. `pipelex init config` creates a **template** configuration file with sample settings. It does not include all possible configuration options - it's meant as a starting point.
    3. Running `pipelex init config` will **overwrite** your existing `pipelex.toml` file without warning. Make sure to backup your configuration before running this command.
    4. Credentials (the `.env` in `~/.pipelex/`) always remain in the global directory regardless of `--local` — only config, inference, and telemetry files are written to the project `.pipelex/`.

For a complete list of all possible configuration options, refer to the configuration group documentation below.

## The home configuration directory: `PIPELEX_HOME`

The global layer lives in `~/.pipelex/` unless the `PIPELEX_HOME` environment variable names another directory. The variable names the directory itself, the equivalent of `~/.pipelex`, not its parent, so it can be any directory whatever its name:

```bash
export PIPELEX_HOME=/path/to/ci/pipelex-home
```

Everything that reads or writes the global layer follows it: its `pipelex.toml` and override files, the inference files and their personal overrides, the credentials in its `.env`, the telemetry configuration, `pipelex init`, `pipelex doctor`, `pipelex update`, `pipelex migrate`, and the agent CLI's `--global` flag. A `~` is expanded, a relative path resolves against the working directory at the moment Pipelex is imported, and an empty value counts as unset.

Every boot fills the directory from the kit's templates, as it does `~/.pipelex/`: it creates the directory when it does not exist and copies in each kit file the directory lacks, never overwriting a file that is there or writing through a symbolic link, and leaving a link or a file that stands where the kit has a directory alone with everything under it. Each file is written whole or not at all, so a copy cut short leaves nothing half-written. A fresh `mktemp -d`, an empty volume mount, or a directory holding only a `.env` or a personal override therefore works as it is, and a directory that already holds every kit file is not written at all. The inference files are the one exception: they are copied as a whole, and only when the directory has no `inference/backends.toml`, so a directory with an inference setup of its own keeps it exactly as it is, and `pipelex init` or `pipelex update` is what changes it; `backends.toml` is written last, so a fill cut short part-way is completed by the next boot. A directory Pipelex cannot write to, such as a read-only mount, is read as it is.

It is meant for any process that should not share the machine's settings: a test run or a CI job that commits a configuration of its own, a container, or a checkout that must not read the developer's personal backends. A project's own `.pipelex/` keeps winning over it, exactly as it wins over `~/.pipelex/`.

!!! warning "Set it before Pipelex is imported"
    The home directory's `.env` is loaded when Pipelex is first imported, so `PIPELEX_HOME` has to be in the process environment by then: set it in the shell, the make target, the CI job or the container image. Set later, from a test fixture or from code that runs after something has imported Pipelex, it moves the configuration files but not the credentials already loaded from the old `.env`. A `.env` file cannot set it either: the home `.env` is found through it, so Pipelex discards a `PIPELEX_HOME` line in the home `.env` or the project's `.env`, and the process keeps the value it was started with.

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

The configuration is organized into five main sections. The first three mirror the layers of the runtime:

1. `[runtime]` - process-scoped infrastructure: storage, secrets, logging, cloud credentials, outbound network posture, reporting, tracing, observation, and the plugin denylist
2. `[inference]` - the model-calling seam: the model deck, LLM, image generation, extraction, the default templating style, and dry-run mocks
3. `[interpreter]` - library-scoped method machinery: MTHDS parsing, pipe runs, pipe functions, pipeline execution, source scanning, and the builder
4. `[run]` - where `pipelex run` and `pipelex-agent run` execute a method by default: on this machine or on the hosted Pipelex API, see [Run Configuration](config-practical/run-config.md)
5. `[kit]` - settings for the `pipelex-dev` kit tooling

Each section contains multiple subsections for specific features and functionalities. A setting's address tells you which layer owns it: `[runtime.*]` applies to any process, whatever it loads; `[interpreter.*]` only means something once a method is loaded.

!!! tip "If your file predates this layout"
    A `pipelex.toml` written against an older layout still boots. Pipelex carries it forward in memory, warns you that it did, and changes nothing on disk; `pipelex doctor` reports the pending migration. `pipelex migrate` is what makes it permanent — it rewrites each file in place and keeps the original beside it as a timestamped `.bak`. Your settings move address, they do not change value. The command walks the global `~/.pipelex/` and your project's `.pipelex/`, so a file you load from somewhere else — through `Pipelex.make(config_dir=…)` — is yours to update where it lives, and the boot warning says so rather than naming a command that would not reach it. Your inference backend definitions under `inference/backends/` are migratable the same way; the [inference backend page](config-technical/inference-backend-config.md) says what a migration will and will not touch in one. See [Migration Ledger](../migration-ledger.md) for what a migration may and may not do to your file.

## Configuration Override System

Pipelex uses a sophisticated configuration override system that loads and merges configurations in a specific order. This allows for fine-grained control over settings in different environments and scenarios.

The exact loading sequence is (later wins, per leaf key):

1. Base configuration from the installed Pipelex package (`pipelex.toml`)
2. Global base configuration (`~/.pipelex/pipelex.toml`, or `pipelex.toml` in the directory `PIPELEX_HOME` names)
3. Global override sequence, from `~/.pipelex/`: `pipelex_local.toml`, `pipelex_{environment}.toml`, `pipelex_{run_mode}.toml`, `pipelex_override.toml`, `pipelex_temporary_override.toml`
4. Your project's base configuration (`{project_root}/.pipelex/pipelex.toml`)
5. Project override sequence, from the project's `.pipelex/`: the same five files as step 3
6. Programmatic overrides passed in code, if any

Notes on the override sequence:

- `pipelex_{environment}.toml` (example: `pipelex_dev.toml`) is selected by the `PIPELEX_ENV` environment variable (see [Selecting the environment](#selecting-the-environment))
- `pipelex_{run_mode}.toml` — example run modes: normal, unit_test; under unit testing the run-mode overlay is sourced exclusively from `./tests/pipelex_{run_mode}.toml`
- Each subsequent configuration file in this sequence can override settings from the previous ones, and project-level files override the global `~/.pipelex/` layer
- The two inference documents, `inference/backends.toml` and `inference/routing_profiles.toml`, are not part of this merge. Each has a single personal override file beside it, `backends_override.toml` and `routing_profiles_override.toml`, merged over the resolved base — global tier first, then project tier. See [Personal overrides](config-technical/inference-backend-config.md#personal-overrides)

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
