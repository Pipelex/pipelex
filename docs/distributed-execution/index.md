---
title: "Distributed Execution"
description: "Run Pipelex methods as durable workflows. Two backends, both built on Temporal: run Pipelex's own Temporal workers, or run pipes inside Mistral's managed Workflows control plane."
---

# Distributed Execution

Pipelex methods run in-process by default — you call `pipelex run pipe ...` or invoke a pipe from Python and everything happens in one process. When you need durability, retries that survive failure, and horizontal scale, you run the same methods as **durable workflows**. There are two backends to do that, and both are durable execution on Temporal underneath.

## The two backends

- **[Pipelex on Temporal](temporal/index.md)** — you run Pipelex's own Temporal workers against a Temporal cluster you operate (self-hosted or Temporal Cloud). You own the control plane. Python 3.10+, installed with `pipelex[temporal]`. Generally available.
- **[Pipelex on Mistral Workflows](mistral-workflows/index.md)** *(preview)* — you run pipes inside Mistral Workflows, Mistral's managed orchestration control plane, which is itself built on Temporal. You don't operate the cluster. Python 3.12+, installed with `pipelex-mistralai-workflows`.

!!! info "Both backends are Temporal underneath"
    They are the same durability primitive, packaged two ways. The difference is *who runs the control plane* — your own Temporal deployment, or Mistral's managed Workflows service. Picking a backend is mostly a question of which control plane you already operate. See [Choosing a Backend](mistral-workflows/choosing-a-backend.md).

## What's shared

The same `.mthds` methods run on either backend without rewriting. Both go through Pipelex's runtime bridge, which classifies controller pipes as child workflows and leaf operators (LLM calls, image generation, document extraction) as activities — so durability, retries, and observability attach at the right granularity regardless of which control plane executes them.

## Where to go next

Pipelex on Temporal:

- **[Overview](temporal/index.md)** — what it is, when you'd want it, the big picture, quick start.
- **[Cluster Setup](cluster-setup.md)** — search attributes and `pipelex setup-temporal-namespace`.
- **[Worker Deployment](workers.md)** — `pipelex worker`, scopes, runtime profiles, multi-worker topologies.
- **[Task-Queue Routing](task-routing.md)** — per-activity routing, queue options, per-handle overrides.
- **[Workflow Observability](observability.md)** — workflow ids, summary fields, search-attribute filtering.

Pipelex on Mistral Workflows *(preview)*:

- **[Overview](mistral-workflows/index.md)** — what it is and how it fits together.
- **[Installation & Preview Status](mistral-workflows/installation.md)** — install the preview package, prerequisites.
- **[Your First Pipelex Workflow](mistral-workflows/your-first-pipelex-workflow.md)** — run a pipe from a Mistral Workflows worker.

To weigh the two against each other, start with [Choosing a Backend](mistral-workflows/choosing-a-backend.md). For the failure-handling model that motivates durable execution, see [Retries & Resilience](../reliability/retries-and-resilience.md).
