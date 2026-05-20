---
title: "Retries & Resilience"
description: "How Pipelex handles transient failures — transport-level retry, the direct vs Temporal contract, and where retry legitimately lives."
---

# Retries & Resilience

AI pipelines fail in transient ways: a provider rate-limits you, a connection drops, a model returns malformed JSON. Pipelex has a deliberate, honest model for handling those failures — and an equally deliberate line about what it does *not* do.

The short version: **direct execution is for simplicity, Temporal execution is for resilience.** Both paths shrug off brief transport blips. Only the Temporal path survives a crash and retries under failure. There is no half-measure pretending otherwise.

---

## The two execution paths

Pipelex runs your `.mthds` methods one of two ways, and they make different promises.

| Path | What it promises | What it does on failure |
|------|------------------|-------------------------|
| **Direct execution** (default) | Simplicity, zero infrastructure | Retries transient *transport* failures via the provider SDK, then surfaces the error |
| **Temporal execution** (opt-in) | Durability and resilience | The same transport retry, plus activity-level retry and crash survival |

Direct execution makes **one pipeline-level attempt**. If a pipe fails after the transport layer has done its retrying, the failure surfaces — the run does not restart, and it does not survive a process crash. That is the intended contract, not a gap. The value of the direct path is that it needs no cluster, no workers, no setup.

When you need retry-under-failure and durability, you run the same methods on [Temporal](../distributed-execution/index.md) — see [When to reach for Temporal](#when-to-reach-for-temporal) below.

---

## The retry model

Retry in Pipelex lives in two well-defined tiers. Nothing retries outside them.

| Tier | What it does | Where it runs | Both paths? |
|------|--------------|---------------|-------------|
| **Tier 1 — Transport retry** | Retries connection errors and HTTP `408` / `409` / `429` / `5xx`, honoring `Retry-After` | Inside the inference SDK / HTTP client | ✅ Yes |
| **Tier 2 — Temporal durability** | Activity-level retry keyed off the error category, plus workflow durability and redelivery | The Temporal worker | ❌ Temporal only |

On the direct path there is **nothing between Tier 1 and Tier 2** — that gap *is* the difference between the two products.

```
Direct execution:    [ Tier 1: transport retry ] → surface the error
Temporal execution:  [ Tier 1: transport retry ] → [ Tier 2: activity retry + durability ]
```

---

## Tier 1 — transport retry

Every inference SDK call retries transient transport failures before giving up. Pipelex makes this an explicit, uniform policy rather than inheriting each provider SDK's silent default.

It is controlled by one top-level setting in `pipelex.toml`:

```toml
[cogt]
transport_max_retries = 2
```

`transport_max_retries` (default `2`) is the number of retries attempted **on top of** the initial request. A value of `2` allows up to 3 attempts total. Retries fire on a connection error or an HTTP `408` / `409` / `429` / `5xx` response, and they honor a `Retry-After` response header when the provider sends one.

This setting is wired uniformly into every inference SDK client — Anthropic, OpenAI / Azure OpenAI, the Pipelex Gateway clients, Mistral, and Google — as well as the raw-HTTP Azure image-generation path. So the retry posture is one deliberate policy across all providers.

!!! info "Transport retry is not pipeline retry"
    Tier 1 retries a *single* HTTP request to a provider. It does not re-run a pipe, re-run a step, or restart a pipeline. If a call still fails after its transport retries are exhausted, the error surfaces.

---

## Structured output — schema re-ask

When a pipe asks an LLM for a structured object, the model sometimes returns JSON that does not match the requested schema. Pipelex re-asks the model on that specific failure, via the `instructor` library.

This is **output shaping, not resilience**. The re-ask happens only on a schema-validation failure — a transport error is *not* re-asked here; it propagates to Tier 1, which is the sole transport-retry layer. The re-ask count is configured separately:

```toml
[cogt.llm_config]
schema_reask_max_attempts = 3   # instructor schema re-ask attempts — distinct from transport_max_retries
```

Keep the two settings distinct in your mind: `transport_max_retries` handles a flaky network; `schema_reask_max_attempts` handles a model that produced the wrong shape.

---

## Bounded fan-out for batches

When `PipeBatch` maps a pipe over a large list, it does not spawn every branch at once. Branches run in bounded concurrent chunks, capped by `max_concurrency` (default `8`):

```toml
[pipelex.pipeline_execution_config]
max_concurrency = 8
```

This is **admission control, not retry** — it stops a batch over thousands of items from triggering a self-inflicted rate-limit storm against your provider. See [PipeBatch](../building-methods/pipes/pipe-controllers/PipeBatch.md#concurrency) for details.

---

## How a failure is classified

Whichever path runs, every inference failure is classified the moment it happens. The classification is what Tier 2 acts on, and it is what reaches you in the error output.

| Category | Meaning | Retried by Temporal? |
|----------|---------|----------------------|
| `transient` | A brief, self-correcting failure (rate limit, 5xx) | ✅ Yes |
| `configuration` | The setup is wrong (bad API key, missing backend) | ❌ No |
| `content` | The input or prompt is wrong (content-policy violation) | ❌ No |
| `capacity` | Account quota or billing exhausted | ❌ No |
| `ambiguous` | Outcome unknown — the call may have committed | ❌ No |
| `unknown` | Could not classify | ❌ No |

Only `transient` failures are worth retrying — re-running a call that failed because your API key is wrong just wastes time and money. On the Temporal path, the activity retry policy uses exactly this signal: a `transient` failure retries, every other category fails fast.

For the full mechanics of how errors are classified, carried, and reported, see [Error Model](../under-the-hood/error-model.md).

---

## When to reach for Temporal

Stay on direct execution while you are developing, prototyping, or running short pipelines where a transient failure is acceptable to just re-run by hand.

Move to [Temporal](../distributed-execution/index.md) when you need:

- **Crash survival** — a long pipeline resumes exactly where it left off after a worker restart.
- **Retry under failure** — each LLM call, extraction, or image generation retries independently, with per-activity timeouts and a retry policy keyed off the error category.
- **Large durable batches** — running a pipe over thousands of items, durably and rate-limited.
- **Horizontal scale** — fan work out across multiple worker machines.

The same `.mthds` methods run on both paths without changing a line — flip `[temporal] is_enabled = true` and the work dispatches through Temporal.

!!! tip "The error you see is the same on both paths"
    A pipe that fails on a Temporal worker reaches your CLI or HTTP adapter with the *same* classification — category, retryable flag, model, provider, suggested action — as the identical failure run locally. Switching to Temporal changes the resilience, not the error contract.

---

## Configuration reference

| Setting | Location | Default | Controls |
|---------|----------|---------|----------|
| `transport_max_retries` | `[cogt]` | `2` | Tier 1 — transport retry attempts per request |
| `schema_reask_max_attempts` | `[cogt.llm_config]` | `3` | `instructor` schema re-ask attempts (structured output) |
| `max_concurrency` | `[pipelex.pipeline_execution_config]` | `8` | `PipeBatch` bounded fan-out (set `"unbounded"` to disable) |
| `is_enabled` | `[temporal]` | `false` | Opt into Temporal execution (Tier 2) |

---

## Next steps

- [Distributed Execution with Temporal](../distributed-execution/index.md) — set up the resilient path
- [Error Model](../under-the-hood/error-model.md) — how failures are classified and reported under the hood
- [Cogt Configuration](../configuration/config-technical/cogt-config.md) — the full `[cogt]` reference
- [PipeBatch](../building-methods/pipes/pipe-controllers/PipeBatch.md) — mapping a pipe over a list, with bounded concurrency
