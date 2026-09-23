---
description: "Understand Pipelex telemetry options — what data is collected, how to opt out, and how privacy works for gateway and anonymous usage streams."
---

# Telemetry

Pipelex supports two independent telemetry streams that serve different purposes. Understanding how they work helps you make informed decisions about data collection.

## Two Telemetry Streams

### 1. Gateway Telemetry (Pipelex-Controlled)

When you use **Pipelex Gateway** as your inference backend, identified telemetry is **automatically enabled**. This telemetry is tied to your Gateway API key (hashed for security) and operates independently from your `telemetry.toml` settings.

**What we collect:**

- Model names used (e.g., `gpt-5.4`, `claude-4.5-sonnet`) and parameters
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
- **Project init** (`pipelex init telemetry --local` — writes to `{project_root}/.pipelex/telemetry.toml`): a fully **commented-out** template is created. The project file is layered on top of your global config, so leaving it commented means the project inherits your global telemetry settings as-is. Uncomment a key only when this project should diverge.

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

## Attaching your own groups to a run

A host that runs Pipelex for more than one customer usually wants a run's telemetry to belong to the entities *it* cares about — an organization, a workspace, a tenant. Pipelex carries those labels for you without ever learning what they mean.

The run-level metadata every run carries (`RunMetadata`) has an `analytics_groups` field: an opaque mapping of **group type** to **group key** that you supply when you start the run, beside `user_id` and `storage_scope`.

```python
analytics_groups = {"organization": "org_acme"}
```

!!! note "What this field does today"
    The runtime validates the mapping, carries it through every nested pipe, and keeps it on the run's metadata across a process boundary. It does **not** yet attach it to the events and spans the built-in PostHog and OpenTelemetry integrations emit — so setting it today will not group anything in your backend. Supply it if you want your runs to carry the labels from now on; wait if you want to see them in PostHog.

The rules it follows:

- **Nothing is privileged.** `organization` is a word a host chose, not one Pipelex knows. A deployment that sends `{"tenant": "t-1", "plan_tier": "enterprise"}` is served identically, because the runtime never reads a key by name — the same boundary that keeps `storage_scope` opaque.
- **It is validated where it enters.** A group type is lowercase snake_case starting with a letter (up to 32 characters); a group key is 1 to 128 characters from `A-Za-z0-9_-`; a run carries at most five group types. A mapping outside those bounds is refused before the run registers itself or emits anything, and again when a bridge payload is decoded — not later, inside a telemetry capture. The group key is quoted into log lines and capture payloads, so whitespace and control characters are refused outright.
- **It is optional.** Omitting it leaves the group facet empty, which misattributes nothing. Unlike `user_id` and `storage_scope`, which have no default because a missing one used to be invented, a missing group invents nothing.
- **It travels with the run.** The mapping rides the job through every nested pipe, and the bridge payload that crosses a process boundary carries it, so a distributed worker is handed the same groups the entry point was given.

These are labels for grouping, not content: they belong in the reserved identity fields of whichever backend understands groups, never in an event property or a span name.

## Privacy

We take your privacy seriously:

- **Gateway telemetry** never collects prompts, completions, or business data
- **Custom telemetry** gives you full control over what data is captured
- PostHog tracing includes privacy controls to redact sensitive content
- All telemetry can be completely disabled

For detailed configuration options, see [Telemetry Configuration](../configuration/config-practical/telemetry-config.md).

For more information about our data practices, see our [Privacy Policy](https://go.pipelex.com/privacy-policy).
