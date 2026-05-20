---
title: "Distributed Execution with Temporal"
description: "Run Pipelex pipelines as durable Temporal workflows across one or more worker processes. Per-activity routing, runtime profiles, and dashboard observability."
---

# Distributed Execution with Temporal

Run your `.mthds` methods as durable Temporal workflows.

## Overview

Pipelex pipelines normally run in-process. With the optional `pipelex[temporal]` integration, the same pipelines run as Temporal workflows: each pipe becomes a workflow, child pipes become child workflows, and every LLM call, image generation, or document extraction becomes an activity. Temporal handles durability, retries, scheduling, and visibility; Pipelex handles the AI work. Flip `[temporal] is_enabled = true` in `pipelex.toml` and the same methods run distributed without changing a line of method code.

## Supported deployment patterns

- **Single worker** — one process polls one task queue, runs everything. Right for most deployments.
- **Router + runners** — a dedicated workflow worker dispatches activities to one or more runner pools (LLM, image-gen, extract). Each runner pool scales independently and isolates failures.
- **Per-provider isolation** — separate worker pools for OpenAI, Anthropic, image generation, and OCR, each on its own task queue with its own retry policy and rate cap.

## Configuration

All knobs live under `[temporal.*]` in `pipelex.toml`:

- `[temporal.search_attributes]` — custom search attributes attached to every workflow start.
- `[temporal.worker_config]` — default task queue, workflow and activity timeouts, baseline retry policy.
- `[temporal.activity_queues.<activity>]` — per-activity, per-handle task-queue routing.
- `[temporal.queue_options.<queue>]` — per-queue timeout, retry, and rate-cap overlays.
- `[temporal.worker_runtime_profiles.profiles.<name>]` — named runtime profiles for `pipelex worker --profile`.
- `[temporal.worker_scopes.scopes.<name>]` — named scopes for `pipelex worker --scope`.
- `[temporal.temporal_config]` — server profiles (`local`, `testing`, …) and log toggles.

## Get started

See the **[Distributed Execution with Temporal](../distributed-execution/index.md)** guide for the full walkthrough — overview, cluster setup, worker deployment, task-queue routing, and workflow observability.
