---
description: "Understand Pipelex telemetry options — what data is collected, how to opt out, and how privacy works for gateway and anonymous usage streams."
---

# Telemetry

Pipelex supports two independent telemetry streams that serve different purposes. Understanding how they work helps you make informed decisions about data collection.

## Two Telemetry Streams

### 1. Gateway Telemetry (Pipelex-Controlled)

When you use **Pipelex Gateway** as your inference backend, identified telemetry is **automatically enabled**. This telemetry is tied to your Gateway API key (hashed for security) and operates independently from your `telemetry.toml` settings.

A run that names a caller of its own is still distinguished on this stream, but never by a value you supplied: the caller's `user_id` is folded one way into your key's hash, so the value you spelled never reaches us, and the same caller name at another deployment is a different person here. Your key's own hash travels beside the fold, so your usage stays countable as yours. Read the fold as a pseudonym rather than as a promise of anonymity: it cannot be reversed, but it is a digest and not a secret, so it is not proof against somebody who already holds a candidate id and wants to check it. Your `analytics_groups` are not forwarded to this stream at all — they are your own vocabulary about your own customers, and they stay on the destinations you control.

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
- A run's `user_id` as you spell it, or its `analytics_groups` in any form

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

On **your own** PostHog stream, every span and every event the run produces is then captured under that run's `user_id`, with the groups attached through PostHog's own groups facet — so a generation made for one of your customers appears on that customer's timeline and inside their organization, instead of under one identity per deployment. The same values reach every OpenTelemetry exporter as the span attributes `pipelex.run.user_id` and `pipelex.run.analytics_groups`, and Langfuse receives the user id in the field it reserves for it. Pipelex's own Gateway stream is the one exception, and it is described above: it receives a one-way digest of the caller and none of your groups.

Anything that names no caller of its own keeps reporting under the `user_id` you configured in `telemetry.toml`, which is what that setting now means: the identity of everything that is not one caller's run. That covers an event outside any run — a CLI command listing your pipes — and a run whose caller is not a distinguishable person either: a run on your own machine is attributed to the literal `local`, the same string on every machine, so Pipelex declines it as an identity and uses your configured id instead. Per-run attribution is for a host that passes a real `user_id` per run.

The groups do not depend on that. A run that leaves `user_id` at its default still carries its `analytics_groups` onto every capture, under your configured id — knowing which entities a run belongs to and naming its caller are two separate decisions, and you may take one without the other.

!!! note "Anonymous mode covers your users too"
    With `mode = "anonymous"`, the runtime identifies nobody on your stream: no run's `user_id` is applied, no groups are sent, and the `user_id` you configured is not sent either — a mode that identifies nobody would not be one that still named you. Leaving a `user_id` in `telemetry.toml` while switching to `anonymous` therefore changes nothing. Per-run attribution needs `mode = "identified"`.

The rules it follows:

- **Nothing is privileged.** `organization` is a word a host chose, not one Pipelex knows. A deployment that sends `{"tenant": "t-1", "plan_tier": "enterprise"}` is served identically, because the runtime never reads a key by name — the same boundary that keeps `storage_scope` opaque.
- **It is validated where it enters.** A group type is lowercase snake_case starting with a letter (up to 32 characters); a group key is 1 to 128 characters from `A-Za-z0-9_-`; a run carries at most five group types. A mapping outside those bounds is refused before the run registers itself or emits anything, and again when a bridge payload is decoded — not later, inside a telemetry capture. The group key is quoted into log lines and capture payloads, so whitespace and control characters are refused outright.
- **It is optional.** Omitting it leaves the group facet empty, which misattributes nothing. Unlike `user_id` and `storage_scope`, which have no default because a missing one used to be invented, a missing group invents nothing.
- **It travels with the run.** The mapping rides the job through every nested pipe, and the bridge payload that crosses a process boundary carries it, so a distributed worker is handed the same groups the entry point was given.

These are labels for grouping, not content: they land in the reserved identity fields of whichever backend understands groups, never in an event property or a span name.

## Privacy

We take your privacy seriously:

- **Gateway telemetry** never collects prompts, completions, or business data
- **Custom telemetry** gives you full control over what data is captured
- PostHog tracing includes privacy controls to redact sensitive content
- All telemetry can be completely disabled

For detailed configuration options, see [Telemetry Configuration](../configuration/config-practical/telemetry-config.md).

For more information about our data practices, see our [Privacy Policy](https://go.pipelex.com/privacy-policy).
