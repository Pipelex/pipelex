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

## Related Configuration

- [Configure AI Providers](../../5-setup/configure-ai-providers.md)
- [Inference Backend Configuration](../../7-configuration/config-technical/inference-backend-config.md)
- [Telemetry Configuration](../../7-configuration/config-practical/telemetry-config.md)

