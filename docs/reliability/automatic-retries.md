---
title: "Automatic Retries"
description: "The always-on mechanisms Pipelex applies on every execution path — transport-level retry, structured-output schema re-ask, and bounded fan-out for batches."
---

# Automatic Retries

Whichever execution path you run, Pipelex applies a fixed set of automatic, bounded mechanisms to absorb transient failures and protect your providers. Transport retry is the one true retry here; the other two — schema re-ask and bounded fan-out — are closely related behaviors that shape output and control load. Together they are the always-on parts of the [retry model](retries-and-resilience.md#the-retry-model).

## Tier 1 — transport retry

Every inference SDK call retries transient transport failures before giving up. Pipelex makes this an explicit, uniform policy rather than inheriting each provider SDK's silent default.

It is controlled by one top-level setting, which you override in your project's `.pipelex/pipelex.toml`:

```toml
[cogt]
transport_max_retries = 2
```

`transport_max_retries` (default `2`) is the number of retries attempted **on top of** the initial request. A value of `2` allows up to 3 attempts total. Retries fire on a connection error or an HTTP `408` / `409` / `429` / `5xx` response, and they honor a `Retry-After` response header when the provider sends one.

This setting is wired into every inference SDK client that exposes a client-side retry budget — Anthropic, OpenAI / Azure OpenAI, the Pipelex Gateway LLM clients, Mistral, and Google — as well as the raw-HTTP Azure image-generation path. So the retry posture is one deliberate policy across those provider SDK clients. (The Pipelex Gateway's document-extraction and image-generation calls go through the Portkey SDK, which has no client-side retry budget; transport retries for those are owned by the gateway itself.)

!!! info "Transport retry is not pipeline retry"
    Tier 1 retries a *single* HTTP request to a provider. It does not re-run a pipe, re-run a step, or restart a pipeline. If a call still fails after its transport retries are exhausted, the error surfaces.

## Structured output — schema re-ask

When a pipe asks an LLM for a structured object, the model sometimes returns JSON that does not match the requested schema. Pipelex re-asks the model on that specific failure, via the `instructor` library.

This is **output shaping, not resilience**. The re-ask happens only on a schema-validation failure — a transport error is *not* re-asked here; it propagates to Tier 1, which is the sole transport-retry layer. The re-ask count is configured separately:

```toml
[cogt.llm_config]
schema_reask_max_attempts = 3   # instructor schema re-ask attempts — distinct from transport_max_retries
```

Keep the two settings distinct in your mind: `transport_max_retries` handles a flaky network; `schema_reask_max_attempts` handles a model that produced the wrong shape.

## Bounded fan-out for batches

When `PipeBatch` maps a pipe over a large list, it does not spawn every branch at once. Branches run in bounded concurrent chunks, capped by `max_concurrency` (default `8`):

```toml
[pipelex.pipeline_execution_config]
max_concurrency = 8
```

This is **admission control, not retry** — it stops a batch over thousands of items from triggering a self-inflicted rate-limit storm against your provider. See [PipeBatch](../building-methods/pipes/pipe-controllers/PipeBatch.md#concurrency) for details.

## Related

- **[Failure Classification](failure-classification.md)** — how each failure is categorized, and which categories are worth retrying.
- **[Durable Execution](durable-execution.md)** — Tier 2: activity-level retry and crash survival on a durable backend.
