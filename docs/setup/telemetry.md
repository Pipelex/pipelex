---
description: "Understand Pipelex telemetry options — what data is collected, how to opt out, and how privacy works for gateway and anonymous usage streams."
---

# Telemetry

Pipelex supports two independent telemetry streams that serve different purposes. Understanding how they work helps you make informed decisions about data collection.

## Two Telemetry Streams

### 1. Gateway Telemetry (Pipelex-Controlled)

When you use **Pipelex Gateway** as your inference backend, identified telemetry is **automatically enabled**. This telemetry is tied to your Gateway API key (hashed for security) and operates independently from your `telemetry.toml` settings.

**What we collect:**

- Model names used (e.g., `gpt-5.2`, `claude-4.5-sonnet`) and parameters
- Pipe types (e.g., `PipeLLM`, `PipeSequence`, etc.)
- Token counts (input/output)
- Latency metrics
- Error rates (without error details)

**What we do NOT collect:**

- Your prompts or completions
- Your pipe codes or output class names
- File contents or business data

This telemetry allows us to:

- Monitor and improve service quality
- Enforce fair usage limits and prevent abuse
- Provide you with usage insights and better support

!!! info "Gateway Telemetry is Optional"
    Using Pipelex Gateway is entirely optional. If you prefer not to send telemetry to Pipelex servers, simply use your own API keys with direct provider backends (OpenAI, Anthropic, Azure, Bedrock, etc.).

### 2. Custom Telemetry (User-Controlled)

Custom telemetry is configured in `.pipelex/telemetry.toml` and allows you to send observability data to **your own** analytics and monitoring systems:

- **PostHog**: Event tracking and AI span tracing with privacy controls
- **Langfuse**: Full LLM observability (receives full span data)
- **OTLP**: Send spans to any OpenTelemetry-compatible backend (receives full span data)

Custom telemetry is completely independent from Gateway telemetry—you can use both, either, or neither.

## Quick Setup

When you run `pipelex init`, a default `telemetry.toml` configuration file is created:

```bash
pipelex init telemetry
```

The behavior depends on the target:

- **Global init** (default — writes to `~/.pipelex/telemetry.toml`): an active template is created with all options disabled. Edit it to enable your preferred telemetry destinations machine-wide.
- **Project init** (`pipelex init --local` — writes to `{project_root}/.pipelex/telemetry.toml`): a fully **commented-out** template is created. The project file is layered on top of your global config, so leaving it commented means the project inherits your global telemetry settings as-is. Uncomment a key only when this project should diverge.

!!! note "Global vs project config"
    Pipelex looks for telemetry config in **both** `~/.pipelex/` (machine-wide) and `{project_root}/.pipelex/` (per-project). Both are deep-merged, with the project file winning on key collisions — your global Langfuse keys keep applying across every project unless a project explicitly overrides them. See [Telemetry Configuration → Global vs project config](../configuration/config-practical/telemetry-config.md#global-vs-project-config) for the full load order.

### Example: Enable PostHog Tracing

```toml
[custom_posthog]
mode = "anonymous"  # or "identified" with user_id
endpoint = "${POSTHOG_ENDPOINT}"
api_key = "${POSTHOG_API_KEY}"

[custom_posthog.tracing]
enabled = true

[custom_posthog.tracing.capture]
content = false        # Don't capture prompts/completions
pipe_codes = true      # Include pipe codes in span names
```

### Example: Enable Langfuse

```toml
[langfuse]
enabled = true
public_key = "${LANGFUSE_PUBLIC_KEY}"
secret_key = "${LANGFUSE_SECRET_KEY}"
```

## DO_NOT_TRACK Global Override

The `DO_NOT_TRACK` environment variable provides a universal way to disable **all** telemetry:

```bash
export DO_NOT_TRACK=1
```

When set, this disables:

- Gateway telemetry (but note: Gateway won't work without telemetry)
- All custom telemetry destinations

!!! warning "Gateway Requires Telemetry"
    If you set `DO_NOT_TRACK=1` while using Pipelex Gateway, the Gateway will not function. Use direct provider backends instead if you need to disable all telemetry.

## Privacy

We take your privacy seriously:

- **Gateway telemetry** never collects prompts, completions, or business data
- **Custom telemetry** gives you full control over what data is captured
- PostHog tracing includes privacy controls to redact sensitive content
- All telemetry can be completely disabled

For detailed configuration options, see [Telemetry Configuration](../configuration/config-practical/telemetry-config.md).

For more information about our data practices, see our [Privacy Policy](https://go.pipelex.com/privacy-policy).
