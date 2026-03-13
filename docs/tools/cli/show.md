---
description: "Inspect your Pipelex configuration, browse pipeline definitions, and list available AI models directly from the command line."
---

# Show Commands

Inspect your Pipelex configuration, pipelines, and available AI models.

## Show Configuration

```bash
pipelex show config
```

Displays the current Pipelex configuration loaded from all sources (default config overridden by user config).

**Examples:**

```bash
# Display current configuration
pipelex show config
```

!!! note
    This shows the main Pipelex configuration but not the inference backend details. Use `pipelex show backends` for backend configuration.

## List All Pipes

```bash
pipelex show pipes
```

Lists all pipes discovered in your project and imported packages, showing their pipe codes and basic information.

**Examples:**

```bash
# List all available pipes
pipelex show pipes
```

This includes:

- Internal Pipelex pipes (like the pipe builder)
- Pipes from your project's `.mthds` files
- Pipes that are part of imported packages

## Show Pipe Definition

```bash
pipelex show pipe PIPE_CODE
```

Displays the complete definition of a specific pipe including inputs, outputs, prompts, model settings, and all configuration.

**Arguments:**

- `PIPE_CODE` - The pipe code to inspect

**Examples:**

```bash
# Show pipe definition
pipelex show pipe analyze_cv_matching
pipelex show pipe write_weekly_report
```

## List AI Models

```bash
pipelex show models BACKEND_NAME [OPTIONS]
```

Lists all available models from a configured backend provider by querying the provider's API.

**Arguments:**

- `BACKEND_NAME` - The backend to query (e.g., `openai`, `anthropic`, `mistral`)

**Options:**

- `--flat`, `-f` - Output in flat CSV format for easy copying into other configuration files

**Examples:**

```bash
# List models
pipelex show models openai
pipelex show models mistral

# List models in flat format
pipelex show models anthropic --flat
```

**Use case:** When configuring new models in your deck, use this command to see what models are available from each provider.

## Show Backends

```bash
pipelex show backends [OPTIONS]
```

Displays all configured inference backends and the active routing profile with its routing rules.

**Options:**

- `--all`, `-a` - Show all backends including disabled ones (by default, only enabled backends are shown)

**Examples:**

```bash
# Show enabled backends and routing profile
pipelex show backends

# Show all backends including disabled ones
pipelex show backends --all
```

**What it displays:**

- Table of configured backends with status, endpoint, and model count
- Active routing profile name and description
- Default backend for the profile
- Routing rules mapping model patterns to backends

## Related Configuration

- [Inference Backend Configuration](../../configuration/config-technical/inference-backend-config.md)
- Backend configuration files: `.pipelex/inference/backends.toml`
- Routing configuration: `.pipelex/inference/routing_profiles.toml`

