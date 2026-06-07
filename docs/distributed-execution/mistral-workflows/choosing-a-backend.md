---
title: "Choosing a Backend"
description: "Pipelex on Temporal vs Pipelex on Mistral Workflows — both are durable execution on Temporal; pick based on who runs the control plane."
---

# Choosing a Backend

Both distributed-execution backends are durable execution on Temporal underneath. They give you the same core guarantees: crash survival, activity-level retries, and deterministic replay (on recovery the workflow re-runs from its event history, reusing already-stored activity results rather than re-executing completed activities). The real choice is **which control plane you want to operate**: your own Temporal deployment, or Mistral's managed Workflows service.

## Side by side

| | Pipelex on Temporal | Pipelex on Mistral Workflows |
|---|---|---|
| **Control plane** | You run it (self-hosted Temporal or Temporal Cloud) | Mistral runs it (managed) |
| **Install** | `pipelex[temporal]` | `pipelex-mistralai-workflows` |
| **Python** | 3.10+ | 3.12+ |
| **How you invoke** | Enable `[temporal] is_enabled` and call `pipe_run(...)` — it dispatches through the Temporal hub | Call a Pipelex activity from inside your Mistral Workflows worker |
| **Best when** | You already operate Temporal, or want full control over the cluster | You're already building on Mistral's platform |
| **Status** | Generally available | Preview |

## When to pick Temporal

- You already run a Temporal cluster or use Temporal Cloud.
- You want to own worker topology, task-queue routing, and retry policy in detail.
- You need the production operational surface available today: cluster setup, multi-worker scaling, per-activity routing, dashboard observability.

## When to pick Mistral Workflows

- You're already building workflows on Mistral's platform and want pipes to run alongside the rest of your orchestration.
- You'd rather not operate a Temporal cluster yourself.
- You're comfortable with a preview integration while the package stabilizes.

## You can run the same methods on either

Your `.mthds` methods don't change between backends. The choice is purely about where they run and who operates the control plane — so you can start in-process, move to one backend, and switch later without rewriting methods.

## Related

- **[Pipelex on Temporal](../temporal/index.md)** — the self-operated backend.
- **[Pipelex on Mistral Workflows](index.md)** — the managed backend (preview).
- **[Retries & Resilience](../../reliability/retries-and-resilience.md)** — the failure-handling model both backends build on.
