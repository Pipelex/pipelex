---
title: "Distributed Execution"
description: "Run Pipelex methods as durable workflows on Temporal with your own Pipelex Temporal workers. A second, managed backend (Mistral Workflows) is coming soon."
---

# Distributed Execution

Pipelex methods run in-process by default — you call `pipelex run pipe ...` or invoke a pipe from Python and everything happens in one process. When you need durability, retries that survive failure, and horizontal scale, you run the same methods as **durable workflows** on Temporal.

## Pipelex on Temporal

**[Pipelex on Temporal](temporal/index.md)** runs Pipelex's own Temporal workers against a Temporal cluster you operate (self-hosted or Temporal Cloud) — you own the control plane. Python 3.10+, installed with `pipelex-temporal`. Generally available.

The same `.mthds` methods run distributed without rewriting. Pipelex's runtime bridge classifies controller pipes as child workflows and leaf operators (LLM calls, image generation, document extraction) as activities — so durability, retries, and observability attach at the right granularity.

## Where to go next

- **[Overview](temporal/index.md)** — what it is, when you'd want it, the big picture, quick start.
- **[Cluster Setup](cluster-setup.md)** — search attributes and `pipelex-temporal setup-namespace`.
- **[Worker Deployment](workers.md)** — `pipelex-temporal worker`, scopes, runtime profiles, multi-worker topologies.
- **[Task-Queue Routing](task-routing.md)** — per-activity routing, queue options, per-handle overrides.
- **[Workflow Observability](observability.md)** — workflow ids, summary fields, search-attribute filtering.

For the failure-handling model that motivates durable execution, see [Retries & Resilience](../reliability/retries-and-resilience.md).

## Coming soon: a managed backend

A second distributed-execution backend — running Pipelex pipes inside **Mistral Workflows**, Mistral's managed orchestration control plane (itself built on Temporal) — is in active development. It runs the same `.mthds` methods through the same runtime bridge, with no cluster for you to operate. Documentation and install instructions will land here once it ships.
