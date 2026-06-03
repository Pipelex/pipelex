---
title: "Distributed Execution"
description: "Run Pipelex methods as durable workflows on either of two backends — your own Temporal cluster, or Mistral's managed Workflows control plane. Both built on Temporal."
---

# Distributed Execution

Run your `.mthds` methods as durable workflows.

## Overview

Pipelex pipelines normally run in-process. When you need durability, retries that survive failure, and horizontal scale, the same pipelines run as durable workflows — each pipe becomes a workflow, child pipes become child workflows, and every LLM call, image generation, or document extraction becomes an activity. The orchestration layer handles durability, retries, scheduling, and visibility; Pipelex handles the AI work, and the same methods run distributed without changing a line of method code.

## Two backends

Both backends are durable execution on Temporal underneath. The difference is who runs the control plane:

- **[Pipelex on Temporal](../distributed-execution/temporal/index.md)** — you run Pipelex's own Temporal workers against a Temporal cluster you operate (self-hosted or Temporal Cloud). Python 3.10+, `pipelex[temporal]`. Generally available.
- **[Pipelex on Mistral Workflows](../distributed-execution/mistral-workflows/index.md)** *(preview)* — you run pipes inside Mistral Workflows, Mistral's managed orchestration control plane (itself built on Temporal). Python 3.12+, `pipelex-mistralai-workflows`.

See [Choosing a Backend](../distributed-execution/mistral-workflows/choosing-a-backend.md) to decide between them.

## Pipelex on Temporal

Flip `[temporal] is_enabled = true` in `.pipelex/pipelex.toml`, install `pipelex[temporal]`, and the same methods run as Temporal workflows on workers you operate.

### Supported deployment patterns

- **Single worker** — one process polls one task queue, runs everything. Right for most deployments.
- **Router + runners** — a dedicated workflow worker dispatches activities to one or more runner pools (LLM, image-gen, extract). Each runner pool scales independently and isolates failures.
- **Per-provider isolation** — separate worker pools for OpenAI, Anthropic, image generation, and OCR, each on its own task queue with its own retry policy and rate cap.

### Configuration

All knobs live under `[temporal.*]` in `.pipelex/pipelex.toml`:

- `[temporal.search_attributes]` — custom search attributes attached to every workflow start.
- `[temporal.worker_config]` — default task queue, workflow and activity timeouts, baseline retry policy.
- `[temporal.activity_queues.<activity>]` — per-activity, per-handle task-queue routing.
- `[temporal.queue_options.<queue>]` — per-queue timeout, retry, and rate-cap overlays.
- `[temporal.worker_runtime_profiles.profiles.<name>]` — named runtime profiles for `pipelex worker --profile`.
- `[temporal.worker_scopes.scopes.<name>]` — named scopes for `pipelex worker --scope`.
- `[temporal.temporal_config]` — server profiles (`local`, `testing`, …) and log toggles.

## Get started

See the **[Distributed Execution](../distributed-execution/index.md)** guide for the full walkthrough. For Temporal: overview, cluster setup, worker deployment, task-queue routing, and workflow observability. For Mistral Workflows *(preview)*: overview, installation, and your first Pipelex workflow.
