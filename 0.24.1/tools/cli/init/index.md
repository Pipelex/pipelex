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

# Review gateway terms
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
  "accept_gateway_terms": true,
  "telemetry_mode": "off"
}
```

All fields are optional:

| Field | Type | Description |
|-------|------|-------------|
| `backends` | `list[str]` | Backend keys to enable (e.g. `openai`, `anthropic`, `pipelex_gateway`). Omit to keep template defaults. |
| `primary_backend` | `str` | Required only when 2+ backends are selected and `pipelex_gateway` is not among them. |
| `accept_gateway_terms` | `bool` | Required when `pipelex_gateway` is in backends. |
| `telemetry_mode` | `str` | `off` (default), `anonymous`, or `identified`. |

**Examples:**

```bash
# Initialize with OpenAI backend (project-level)
pipelex-agent init --config '{"backends": ["openai"], "telemetry_mode": "off"}'

# Initialize globally with gateway
pipelex-agent init -g --config '{"backends": ["pipelex_gateway"], "accept_gateway_terms": true}'
```

## Related Configuration

- [Configure AI Providers](../../get-started/configure-ai-providers.md)
- [Inference Backend Configuration](../../configuration/config-technical/inference-backend-config.md)
- [Telemetry Configuration](../../configuration/config-practical/telemetry-config.md)

