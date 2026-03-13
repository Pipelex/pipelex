# Telemetry Configuration

## Overview

Telemetry configuration is stored in `.pipelex/telemetry.toml`. This file controls **your custom telemetry** destinations—where you want to send observability data for your own analytics and monitoring.

!!! info "Two Telemetry Streams"
    Pipelex has two independent telemetry streams:

    1. **Gateway Telemetry** (Pipelex-controlled): Automatic when using Pipelex Gateway, tied to your API key
    2. **Custom Telemetry** (User-controlled): Configured in this file, sent to your own backends

    For an overview, see [Telemetry Setup](../../setup/telemetry.md).

## Configuration File Location

```
.pipelex/telemetry.toml
```

This file is created when you run `pipelex init telemetry` or `pipelex init`.

## Full Example Configuration

```toml
# PostHog Configuration (Event tracking + AI span tracing)
[custom_posthog]
mode = "anonymous"                                   # "off" | "anonymous" | "identified"
# user_id = "your_user_id"                           # Required when mode = "identified"
endpoint = "${POSTHOG_ENDPOINT}"                     # Default: https://us.i.posthog.com
api_key = "${POSTHOG_API_KEY}"                       # Get from PostHog Project Settings
geoip = true                                         # Enable GeoIP lookup
debug = false                                        # Enable PostHog debug mode
redact_properties = [
    "prompt",
    "system_prompt", 
    "response",
    "file_path",
    "url",
]                                                    # Event properties to redact

# AI span tracing to YOUR PostHog
[custom_posthog.tracing]
enabled = true                                       # Send AI spans to your PostHog

# Privacy controls for data sent to YOUR PostHog only
[custom_posthog.tracing.capture]
content = false                                      # Capture prompt/completion content
content_max_length = 1000                            # Max length for captured content
pipe_codes = true                                    # Include pipe codes in span names
output_class_names = true                            # Include output class names in spans

# Portkey SDK Configuration
[custom_portkey]
force_debug_enabled = false                          # Force-enable Portkey SDK debug mode
force_tracing_enabled = false                        # Force-enable Portkey SDK tracing

# Langfuse Integration (receives FULL span data, no redaction)
[langfuse]
enabled = true
endpoint = "https://cloud.langfuse.com"              # Override for self-hosted Langfuse
public_key = "${LANGFUSE_PUBLIC_KEY}"
secret_key = "${LANGFUSE_SECRET_KEY}"

# Additional OTLP Exporters (array, receives FULL span data)
[[otlp]]
name = "my-collector"                                # Identifier for logging
endpoint = "https://otel.example.com/v1/traces"      # OTLP endpoint URL
headers = { Authorization = "Bearer ${OTLP_AUTH_TOKEN}" }
```

---

## PostHog Configuration

The `[custom_posthog]` section configures event tracking and optional AI span tracing to your own PostHog instance.

### `[custom_posthog]` Settings

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `mode` | string | `"off"` | Telemetry mode: `"off"`, `"anonymous"`, or `"identified"` |
| `user_id` | string | (none) | Required when `mode = "identified"` |
| `endpoint` | string | `"https://us.i.posthog.com"` | PostHog endpoint URL |
| `api_key` | string | (required) | Your PostHog project API key |
| `geoip` | boolean | `true` | Enable GeoIP lookup for location data |
| `debug` | boolean | `false` | Log events locally without sending |
| `redact_properties` | array | `[]` | Event properties to redact before sending |

#### Mode Options

- **`"off"`**: No events sent to your PostHog
- **`"anonymous"`**: Events sent without user identification
- **`"identified"`**: Events sent with your `user_id` for cross-session tracking

### `[custom_posthog.tracing]` Settings

Controls AI span tracing to your PostHog instance.

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `enabled` | boolean | `false` | Send AI spans to your PostHog |

### `[custom_posthog.tracing.capture]` Settings

Privacy controls for what data is included in spans sent to **your** PostHog.

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `content` | boolean | `false` | Capture prompt/completion content |
| `content_max_length` | integer | (unlimited) | Max length for captured content |
| `pipe_codes` | boolean | `false` | Include pipe codes in span names/attributes |
| `output_class_names` | boolean | `false` | Include output class names in spans |

!!! warning "Privacy Note"
    These capture settings only affect data sent to **your** PostHog. Langfuse and OTLP exporters always receive full span data without redaction.

---

## Portkey SDK Configuration

The `[custom_portkey]` section configures the Portkey SDK behavior when using a custom Portkey backend (not the Pipelex Gateway).

### `[custom_portkey]` Settings

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `force_debug_enabled` | boolean | `false` | Force-enable Portkey SDK debug mode regardless of backend setting |
| `force_tracing_enabled` | boolean | `false` | Force-enable Portkey SDK tracing regardless of backend setting |

!!! info "When to Use"
    These settings are useful when you want to enable Portkey debugging or tracing globally without modifying individual backend configurations.

---

## Langfuse Configuration

The `[langfuse]` section enables integration with [Langfuse](https://langfuse.com/) for LLM observability.

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `enabled` | boolean | `false` | Enable Langfuse integration |
| `endpoint` | string | `"https://cloud.langfuse.com"` | Langfuse endpoint (override for self-hosted) |
| `public_key` | string | (required if enabled) | Langfuse public key |
| `secret_key` | string | (required if enabled) | Langfuse secret key |

!!! info "Full Data"
    Langfuse receives **full span data** including prompts, completions, and all metadata. There is no redaction applied.

---

## OTLP Exporters Configuration

The `[[otlp]]` section is an **array** that allows you to configure multiple OpenTelemetry Protocol exporters.

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `name` | string | (required) | Identifier for logging |
| `endpoint` | string | (required) | OTLP endpoint URL |
| `headers` | object | `{}` | HTTP headers for authentication |

### Example: Multiple OTLP Exporters

```toml
[[otlp]]
name = "datadog"
endpoint = "https://trace.agent.datadoghq.com/v1/traces"
headers = { "DD-API-KEY" = "${DD_API_KEY}" }

[[otlp]]
name = "honeycomb"
endpoint = "https://api.honeycomb.io/v1/traces"
headers = { "x-honeycomb-team" = "${HONEYCOMB_API_KEY}" }
```

!!! info "Full Data"
    OTLP exporters receive **full span data** including prompts, completions, and all metadata. There is no redaction applied.

---

## Environment Variable Substitution

All string values in `telemetry.toml` support environment variable substitution using the `${VAR_NAME}` syntax:

```toml
[custom_posthog]
endpoint = "${POSTHOG_ENDPOINT}"
api_key = "${POSTHOG_API_KEY}"

[langfuse]
public_key = "${LANGFUSE_PUBLIC_KEY}"
secret_key = "${LANGFUSE_SECRET_KEY}"

[[otlp]]
headers = { Authorization = "Bearer ${OTLP_AUTH_TOKEN}" }
```

This allows you to keep sensitive credentials in environment variables or `.env` files rather than committing them to version control.

### Variable Syntax Options

| Syntax | Description |
|--------|-------------|
| `${VAR_NAME}` | Use secrets provider (default: environment variable) |
| `${env:VAR_NAME}` | Force environment variable |
| `${secret:VAR_NAME}` | Force secrets provider |
| `${env:VAR\|secret:FALLBACK}` | Try env first, then secret as fallback |

---

## DO_NOT_TRACK Override

The `DO_NOT_TRACK` environment variable disables **all** telemetry globally:

```bash
# Linux/macOS
export DO_NOT_TRACK=1

# Windows PowerShell
$env:DO_NOT_TRACK = "1"

# Windows CMD
set DO_NOT_TRACK=1
```

When set, this disables:

- All custom telemetry (PostHog, Langfuse, OTLP)
- Gateway telemetry (note: Gateway won't work without telemetry)

---

## Resetting Configuration

To reset your telemetry configuration to defaults:

```bash
rm .pipelex/telemetry.toml
pipelex init telemetry
```

---

## Privacy and Compliance

- **Custom telemetry** gives you full control over what data is captured and where it's sent
- **PostHog tracing** includes granular privacy controls via the `capture` settings
- **Langfuse and OTLP** receive full data—configure these only if you're comfortable with that
- The `DO_NOT_TRACK` environment variable provides a global kill switch

For more information about our data practices, see our [Privacy Policy](https://go.pipelex.com/privacy-policy).
