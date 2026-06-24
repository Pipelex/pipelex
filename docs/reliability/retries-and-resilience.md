---
title: "Retries & Resilience"
description: "How Pipelex handles transient failures — transport-level retry, the direct vs durable-execution contract, and where retry legitimately lives."
---

# Retries & Resilience

AI pipelines fail in transient ways: a provider rate-limits you, a connection drops, a model returns malformed JSON. Pipelex has a deliberate, honest model for handling those failures — and an equally deliberate line about what it does *not* do.

The short version: **direct execution is for simplicity, durable execution is for resilience.** Both paths shrug off brief transport blips. Only the durable path survives a crash and retries under failure. There is no half-measure pretending otherwise.

---

## The two execution paths

Pipelex runs your `.mthds` methods one of two ways, and they make different promises.

| Path | What it promises | What it does on failure |
|------|------------------|-------------------------|
| **Direct execution** (default) | Simplicity, zero infrastructure | Retries transient *transport* failures via the provider SDK, then surfaces the error |
| **Durable execution** (opt-in) | Durability and resilience | The same transport retry, plus activity-level retry and crash survival |

Direct execution makes **one pipeline-level attempt**. If a pipe fails after the transport layer has done its retrying, the failure surfaces — the run does not restart, and it does not survive a process crash. That is the intended contract, not a gap. The value of the direct path is that it needs no cluster, no workers, no setup.

When you need retry-under-failure and durability, you run the same methods on a durable backend — see [Durable Execution](durable-execution.md).

---

## The retry model

Retry in Pipelex lives in two well-defined tiers. Nothing retries outside them.

| Tier | What it does | Where it runs | Both paths? |
|------|--------------|---------------|-------------|
| **[Tier 1 — Transport retry](automatic-retries.md)** | Retries connection errors and HTTP `408` / `409` / `429` / `5xx`, honoring `Retry-After` | Inside the inference SDK / HTTP client | ✅ Yes |
| **[Tier 2 — Durable retry](durable-execution.md)** | Activity-level retry keyed off the error category, plus workflow durability and redelivery | The durable backend's worker | ❌ Durable only |

On the direct path there is **nothing between Tier 1 and Tier 2** — that gap *is* the difference between the two products.

```
Direct execution:    [ Tier 1: transport retry ] → surface the error
Durable execution:   [ Tier 1: transport retry ] → [ Tier 2: activity retry + durability ]
```

This section goes deeper on each piece:

- **[Automatic Retries](automatic-retries.md)** — Tier 1 transport retry, structured-output re-ask, and bounded fan-out — the always-on mechanisms.
- **[Failure Classification](failure-classification.md)** — how each failure is categorized, and which categories are worth retrying.
- **[Durable Execution](durable-execution.md)** — Tier 2: crash survival and retry-under-failure on a durable backend.

---

## Configuration reference

| Setting | Location | Default | Controls |
|---------|----------|---------|----------|
| `transport_max_retries` | `[cogt]` | `2` | Tier 1 — transport retry attempts per request |
| `schema_reask_max_attempts` | `[cogt.llm_config]` | `3` | `instructor` schema re-ask attempts (structured output) |
| `max_concurrency` | `[pipelex.pipeline_execution_config]` | `8` | `PipeBatch` bounded fan-out (set `"unbounded"` to disable) |

Durable execution (Tier 2) is **not** a core configuration toggle. You opt into it by booting the process under an orchestrator plugin — `plugins.boot_orchestrator` (config), `--orchestrator <name>` (CLI), or `Pipelex.make(boot_orchestrator=...)` (Python) — delivered through Pipelex's [durable execution offer](https://pipelex.com/products#durable-execution). See [Durable Execution](durable-execution.md) and [Distributed Execution](../distributed-execution/index.md).

---

## Next steps

- [Automatic Retries](automatic-retries.md) — the always-on transport retry, re-ask, and fan-out mechanisms
- [Failure Classification](failure-classification.md) — how failures are categorized and which ones retry
- [Durable Execution](durable-execution.md) — when to move to a durable backend, and what it adds
- [Distributed Execution](../distributed-execution/index.md) — set up the durable backend (Temporal or Mistral Workflows)
- [Error Model](../under-the-hood/error-model.md) — how failures are classified and reported under the hood
- [Cogt Configuration](../configuration/config-technical/cogt-config.md) — the full `[cogt]` reference
