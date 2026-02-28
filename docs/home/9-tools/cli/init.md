# Init Commands

Initialize project configuration files in your project's `.pipelex` directory.

## Initialize Configuration

```bash
pipelex init [FOCUS]
```

Creates the `.pipelex` directory structure, copies default configuration files, and guides you through backend and telemetry setup.

!!! note "Config updates not yet supported"
    The `pipelex init` command always performs a full reset of the configuration. Incremental config updates will be supported in a future release.

**Arguments:**

- `FOCUS` - What to initialize (optional):
    - `all` (default) - Initialize everything
    - `config` - Only configuration files
    - `inference` - Only inference backend setup
    - `routing` - Only routing profile setup
    - `telemetry` - Only telemetry configuration

**Examples:**

```bash
# Initialize everything (recommended for first-time setup)
pipelex init

# Initialize only configuration files
pipelex init config

# Reconfigure inference backends
pipelex init inference

# Reconfigure telemetry settings
pipelex init telemetry
```

## What Gets Initialized

This command creates the `.pipelex/` directory with:

- **pipelex.toml** - Main configuration file for logging, reporting, etc.
- **inference/** - AI backend and routing configuration
    - `backends.toml` - Backend provider settings
    - `routing_profiles.toml` - Model routing rules
    - `backends/` - Individual backend configuration files
    - `deck/` - AI model aliases and presets
- **telemetry.toml** - Telemetry and observability settings

## Interactive Setup Flow

When you run `pipelex init`, you'll be guided through:

1. **Backend Selection** - Choose which AI providers to enable (OpenAI, Anthropic, Mistral, Pipelex Gateway, etc.)
2. **Routing Configuration** - Set up how models are routed to backends
3. **Telemetry Setup** - Configure observability and analytics

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

- [Configure AI Providers](../../5-setup/configure-ai-providers.md)
- [Inference Backend Configuration](../../7-configuration/config-technical/inference-backend-config.md)
- [Telemetry Configuration](../../7-configuration/config-practical/telemetry-config.md)

