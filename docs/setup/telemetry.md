---
description: "Understand Pipelex telemetry options — what data is collected, how to opt out, and how privacy works for gateway and anonymous usage streams."
---

# Telemetry

Pipelex supports two independent telemetry streams that serve different purposes. Understanding how they work helps you make informed decisions about data collection.

## Two Telemetry Streams

### 1. Gateway Telemetry (Pipelex-Controlled)

When you use **Pipelex Gateway** as your inference backend, identified telemetry is **automatically enabled**. This telemetry is tied to your Gateway API key (hashed for security) and operates independently from your `telemetry.toml` settings.

Test runs are the exception, and either of two signals marks one. The first is the `pytest` or `ci` integration mode. The second is a test run mode, which Pipelex's shared pytest plugin (`pipelex.test_extras.shared_pytest_plugins`) sets for every session that loads it, when pytest configures and before it collects anything, so a suite booting with `Pipelex.make()` in the default mode is covered too, whether it boots in a fixture, at test-module import or in a pytest hook that runs after `pytest_configure`. What it cannot reach is anything pytest runs before it configures: the body of every `conftest.py` loaded at startup, which means the ones along the paths given on the command line or in `testpaths` and not only the one that loads the plugin, and the hooks that run before `pytest_configure`, such as `pytest_addoption` or `pytest_cmdline_main`. Boot in a fixture there. In a test run the Gateway stream stays off, so a project's test suite sends nothing to Pipelex even with the Gateway enabled: the boot does not look for `PIPELEX_GATEWAY_API_KEY` on the stream's behalf, and `DO_NOT_TRACK` does not conflict with the Gateway. The Gateway's Portkey request logging and trace correlation follow the stream, so the `debug` setting on the `pipelex_gateway` backend and the `[pipelex_gateway.portkey]` force flags in `telemetry.toml` have no effect in a test run either, even where your own custom stream is allowed in that mode.

A run that names a caller of its own is attributed to that caller on this stream too: the run's `user_id` is sent as the `distinct_id` exactly as you supplied it, and its `extras` ride the capture as groups. Anything that names no caller reports under your key's hash.

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

### Pipelex's spans in your process

Either stream makes Pipelex trace a run: the Gateway stream whenever it is on, and yours when AI span tracing is enabled on your PostHog. Pipelex's tracer stays its own and never becomes the global one, so your own spans never reach Pipelex's exporters, and **Pipelex never makes its spans current in your process's OpenTelemetry context**:

- Your own instrumentation, an HTTP client's or a provider SDK's, keeps opening its spans under your own current span, in your own trace, while a Pipelex run goes. It is never re-parented under a pipe or an LLM call, nor kept by a sampler that follows its parent because a Pipelex span was sampled.
- An error tracker that reads OpenTelemetry's current span sees yours, not Pipelex's.
- The `json` and `otlp` log sinks still join each line to the Pipelex span it was logged in, the pipe's or the LLM call's, which Pipelex keeps in a context variable of its own, and outside a Pipelex run to your current span, as [Logging](../tools/logging.md#the-trace-context) describes.

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

- Gateway telemetry (but note: outside a test run, Gateway won't work without telemetry)
- All custom telemetry destinations

!!! warning "Gateway Requires Telemetry"
    If you set `DO_NOT_TRACK=1` while using Pipelex Gateway, the Gateway will not function, except in a test run, where the Gateway stream is off anyway. Use direct provider backends instead if you need to disable all telemetry.

## Attaching your own labels to a run

A host that runs Pipelex for more than one customer usually wants a run's telemetry to belong to the entities *it* cares about — an organization, a workspace, a tenant. Pipelex carries those labels for you without ever learning what they mean.

The run-level metadata every run carries (`RunMetadata`) has an `extras` field: an opaque mapping of string keys to string values that you supply when you start the run, beside `user_id` and `storage_scope`. Pipelex never reads a key by name; the telemetry layer forwards the whole mapping as the **groups** of each capture, each key being a group type and its value a group key. Keys are lowercase snake_case starting with a letter (at most 32 characters), values use only letters, digits, `_` and `-` (1 to 128 characters), and a run carries at most five entries; anything else is refused before the run starts.

```python
extras = {"organization": "org_acme"}
```

On **your own** PostHog stream, every span and every event the run produces is then captured under that run's `user_id`, with its extras attached through PostHog's own groups facet — so a generation made for one of your customers appears on that customer's timeline and inside their organization, instead of under one identity per deployment. The same values reach every OpenTelemetry exporter as the span attributes `pipelex.run.user_id` and `pipelex.run.extras`, and Langfuse receives the user id in the field it reserves for it. Pipelex's own Gateway stream receives the same `user_id` and groups, as described above.

Anything that names no caller of its own keeps reporting under the `user_id` you configured in `telemetry.toml`, which is what that setting now means: the identity of everything that is not one caller's run. That covers an event outside any run — a CLI command listing your pipes — and a run whose caller is not a distinguishable person either: a run on your own machine is attributed to the literal `local`, the same string on every machine, so Pipelex declines it as an identity and uses your configured id instead. The same goes for `single-tenant`, which pipelex-api states for every run when it is deployed with no users. Per-run attribution is for a host that passes a real `user_id` per run.

The extras do not depend on that. A run that leaves `user_id` at its default still carries its `extras` onto every capture, under your configured id — knowing which entities a run belongs to and naming its caller are two separate decisions, and you may take one without the other.

### Work that is not a run, and crashes

A run is not the only thing a host does on a caller's behalf. Validating a bundle dry-runs its pipes without being a run, and an unhandled exception reaches PostHog through the interpreter's exception hook, which is handed nothing but the error. Both are still attributed to the caller when one is known, so your configured `user_id` stands only for work that truly belongs to nobody:

- **Validation.** The validate entry points take a `caller_identity` — the `user_id` and `extras` you would state on a run, as a `CallerIdentity`. `PipelexMTHDSProtocol.validate` passes the caller the protocol was built for, `validate_bundles_in_process`, `validate_bundle` and `BundleValidator` accept one directly, and the `BundleValidatorProtocol` seam requires one (`None` meaning "nobody"). The `pipe_dry_run` event and every dry run the validation performs are then attributed to that caller. A CLI validation on your own machine names nobody and keeps reporting under your configured id.
- **Crashes inside a run.** Every pipe runs with its run's caller in scope, and an exception that escapes the pipe carries that caller with it — through any error a host raises `from` it — so an `$exception` captured once the error reaches the interpreter lands on the person whose run failed, with their groups. An exception raised outside every run reports under your configured id.
- **Anything else with no run in hand.** An event emitted without a run but while a caller is in scope reads that caller. A host can open such a scope around its own work with `scoped_caller_identity(caller_identity=...)` from `pipelex.system.caller_identity`.

The same rules apply to all of these as to a run: a placeholder such as `local` names nobody, `mode = "anonymous"` identifies nobody, and the caller never becomes an event property.

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
