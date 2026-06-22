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
- **Retry under failure** — each LLM call, extraction, or image generation retries independently, with per-activity timeouts and a retry policy keyed off the [error category](failure-classification.md). (This per-leaf retry is the Temporal model, where each leaf maps to one host activity. On Mistral Workflows in `direct` mode the whole pipe runs inside a single host activity, so it retries as a unit; per-leaf retry there needs `mistralai-workflows` mode.)
- **Large durable batches** — running a pipe over thousands of items, durably and rate-limited.
- **Horizontal scale** — fan work out across multiple worker machines.

The same `.mthds` methods run on every path without changing a line — which durable backend runs them is a deployment choice, not a code change. The [Pipelex on Temporal](../distributed-execution/temporal/index.md) backend is switched on with `[temporal] is_enabled = true`, which dispatches the work through your Temporal cluster. A second, managed backend (Mistral Workflows) is coming soon: that flag will not apply to it — pipes run inside Workflows activities via the runtime bridge.

!!! note "Durable backend"
    Durable execution (Tier 2) runs on Temporal: your own Temporal cluster ([Pipelex on Temporal](../distributed-execution/temporal/index.md)). A managed option — Mistral's Workflows control plane, also built on Temporal — is coming soon; the resilience model described here will apply to it too, the difference being who operates the control plane.

!!! tip "The error you see is the same on both paths"
    A pipe that fails on a Temporal worker reaches your CLI or HTTP adapter with the *same* classification — category, retryable flag, model, provider, suggested action — as the identical failure run locally. Switching to a durable backend changes the resilience, not the error contract.

## Related

- **[Distributed Execution](../distributed-execution/index.md)** — set up a durable backend (Temporal or Mistral Workflows).
- **[Failure Classification](failure-classification.md)** — the categories the Tier 2 retry policy keys off.
