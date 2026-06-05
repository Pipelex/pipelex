---
title: "Durable Execution"
description: "Tier 2 resilience — when to move from direct execution to a durable backend for crash survival, retry-under-failure, and horizontal scale."
---

# Durable Execution

Direct execution makes one pipeline-level attempt and surfaces the error if it fails. **Durable execution** (Tier 2) adds activity-level retry and crash survival on top of the [automatic retries](automatic-retries.md) that run on every path. This is the resilient path described in the [retry model](retries-and-resilience.md#the-retry-model).

## When to reach for it

Stay on direct execution while you are developing, prototyping, or running short pipelines where a transient failure is acceptable to just re-run by hand.

Move to a [durable backend](../distributed-execution/index.md) when you need:

- **Crash survival** — a long pipeline resumes exactly where it left off after a worker restart.
- **Retry under failure** — each LLM call, extraction, or image generation retries independently, with per-activity timeouts and a retry policy keyed off the [error category](failure-classification.md).
- **Large durable batches** — running a pipe over thousands of items, durably and rate-limited.
- **Horizontal scale** — fan work out across multiple worker machines.

The same `.mthds` methods run on every path without changing a line — which durable backend runs them is a deployment choice, not a code change. The [Pipelex on Temporal](../distributed-execution/temporal/index.md) backend is switched on with `[temporal] is_enabled = true`, which dispatches the work through your Temporal cluster. The [Mistral Workflows](../distributed-execution/mistral-workflows/index.md) backend is wired differently: that flag does not apply — Pipelex pipes run inside Workflows activities via the runtime bridge.

!!! note "Two durable backends"
    Durable execution (Tier 2) is available on two backends, both built on Temporal: your own Temporal cluster ([Pipelex on Temporal](../distributed-execution/temporal/index.md)), and Mistral's managed Workflows control plane ([Pipelex on Mistral Workflows](../distributed-execution/mistral-workflows/index.md), preview). The resilience model described here applies to both; they differ in who operates the control plane. See [Choosing a Backend](../distributed-execution/mistral-workflows/choosing-a-backend.md).

!!! tip "The error you see is the same on both paths"
    A pipe that fails on a Temporal worker reaches your CLI or HTTP adapter with the *same* classification — category, retryable flag, model, provider, suggested action — as the identical failure run locally. Switching to a durable backend changes the resilience, not the error contract.

## Related

- **[Distributed Execution](../distributed-execution/index.md)** — set up a durable backend (Temporal or Mistral Workflows).
- **[Failure Classification](failure-classification.md)** — the categories the Tier 2 retry policy keys off.
