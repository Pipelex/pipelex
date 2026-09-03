---
description: "Initialize your Pipelex project configuration — create .pipelex directory structure, set up backends, and configure telemetry destinations."
---

# Init Commands

Initialize Pipelex configuration files and related setup flows.

## Initialize Configuration

```bash
pipelex init [FOCUS]
pipelex init --local [FOCUS]
```

By default, `pipelex init` writes to the global config directory at `~/.pipelex/`. Use `--local` to create a project-level `.pipelex/` directory at the detected project root. Credentials and Gateway service terms always remain in the global `~/.pipelex/` directory regardless of `--local`.

!!! note "Config updates not yet supported"
    The `pipelex init` command always performs a full reset of the configuration. Incremental config updates will be supported in a future release.

**Arguments:**

- `FOCUS` - What to initialize (optional):
    - `all` (default) - Initialize everything
    - `agreement` - Review or accept Pipelex Gateway terms
    - `config` - Only configuration files
    - `credentials` - Prompt for missing credentials only
    - `inference` - Only inference backend setup
    - `routing` - Only routing profile setup
    - `telemetry` - Only telemetry configuration

**Examples:**

```bash
# Initialize global config (recommended for first-time setup)
pipelex init

# Initialize project-local config
pipelex init --local

# Initialize only configuration files
pipelex init config

# Prompt only for missing credentials
pipelex init credentials

# Reconfigure inference backends
pipelex init inference

# Reconfigure telemetry settings
pipelex init telemetry

# Review the Pipelex service terms
pipelex init agreement
```

## What Gets Initialized

This command creates or resets a Pipelex config directory with:

- **pipelex.toml** - Main configuration file for logging, reporting, etc.
- **inference/** - AI backend and routing configuration
    - `backends.toml` - Backend provider settings
    - `routing_profiles.toml` - Model routing rules
    - `backends/` - Individual backend configuration files
    - `deck/` - AI model aliases and presets
- **telemetry.toml** - Telemetry and observability settings
- **.gitignore** - Keeps Pipelex's own transient copies out of your `git status` — the timestamped `.bak` files [`pipelex migrate`](migrate.md) leaves beside each file it rewrites. Commit it so your teammates get the same. It is written only when the directory has no `.gitignore`; one already there is never modified.

!!! warning "Init writes a fresh file — it does not update one"
    Every `init` target replaces the file with the template, so whatever was in it is gone. If a configuration file has simply fallen behind the current schema, [`pipelex migrate`](migrate.md) is the command: it rewrites the file in place and keeps every setting — your PostHog key, your Langfuse credentials, your exporters. `pipelex doctor` tells you which of the two you have.

!!! note "Offline cache priming"
    When any Pipelex-managed gateway backend is enabled, `pipelex init` also primes an on-disk copy of the published remote config at `~/.pipelex/cache/remote_config.json`. This lets later setup, validation, and dry-runs work even when the remote config service is briefly unreachable. If you run `pipelex init` while offline, it prints a yellow warning and skips priming — re-run it online to enable offline dry-runs.

## Interactive Setup Flow

When you run `pipelex init`, Pipelex can guide you through:

1. **Config reset** - Recreate the selected config files
2. **Backend selection** - Choose which AI providers to enable
3. **Credential prompts** - Fill in missing keys when relevant
4. **Routing configuration** - Set up how models are routed to backends
5. **Telemetry setup** - Configure observability and analytics

## Non-Interactive Init (`pipelex-agent init`)

For automated or agent-driven setups, use the `pipelex-agent` CLI:

```bash
pipelex-agent init [--config/-c JSON] [--global/-g]
```

**Target directory:**

- **Default:** project-level `.pipelex/` at the detected project root (looks for `.git`, `pyproject.toml`, etc.). Errors out if no project root is found.
- **`--global`/`-g`:** forces `~/.pipelex/`.

**Config JSON schema:**

```json
{
  "backends": ["openai", "anthropic"],
  "primary_backend": "openai",
  "accept_gateway_terms": true
}
```

All fields are optional:

| Field | Type | Description |
|-------|------|-------------|
| `backends` | `list[str]` | Backend keys to enable (e.g. `openai`, `anthropic`, `pipelex_gateway`, `pipelex_manifold`). Omit to keep template defaults. |
| `primary_backend` | `str` | Required only when 2+ backends are selected and `pipelex_gateway` is not among them. |
| `accept_gateway_terms` | `bool` | Required when any Pipelex-managed gateway backend (`pipelex_gateway`, `pipelex_manifold`) is in backends. The terms are the Pipelex service's, so one acceptance covers every managed backend. |

Telemetry is not configured via `--config`: init seeds a `telemetry.toml` from a template (a global init writes an active one; a project init drops a commented-out one).

**Examples:**

```bash
# Initialize with OpenAI backend (project-level)
pipelex-agent init --config '{"backends": ["openai"]}'

# Initialize globally with gateway
pipelex-agent init -g --config '{"backends": ["pipelex_gateway"], "accept_gateway_terms": true}'
```

## Related Configuration

- [Configure AI Providers](../../get-started/configure-ai-providers.md)
- [Inference Backend Configuration](../../configuration/config-technical/inference-backend-config.md)
- [Telemetry Configuration](../../configuration/config-practical/telemetry-config.md)

