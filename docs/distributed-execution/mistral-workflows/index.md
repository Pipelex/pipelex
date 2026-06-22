---
title: "Pipelex on Mistral Workflows"
description: "Preview: run Pipelex pipes inside Mistral Workflows, Mistral's managed orchestration control plane built on Temporal, via the pipelex-mistralai-workflows package."
---

# Pipelex on Mistral Workflows

!!! warning "Preview"
    The `pipelex-mistralai-workflows` package is in preview and under active development. Install it with `pip install pipelex-mistralai-workflows` (Python 3.12+). APIs may change, and some integration symbols shown in this guide are illustrative — they are flagged where they appear. Pipelex itself supports Python 3.10+; only this orchestration path needs 3.12.

> Mistral Workflows is an orchestration control plane designed to accelerate the development and reliable execution of complex, AI-driven workflows. Built on Temporal for fault-tolerant workflow execution, Workflows combines a user-friendly API with a rich Python framework optimized for Mistral's AI services.

This guide shows how to run your Pipelex `.mthds` methods *inside* Mistral Workflows — so a single Mistral Workflows worker can orchestrate Pipelex pipes alongside the rest of your AI workflow, with durability, retries, and observability handled by the platform.

## How it fits together

You don't rewrite your methods. The same pipes that run in-process locally run unchanged here:

- You write a Mistral Workflows worker (workflows and activities) the usual way.
- Inside an activity, you invoke a Pipelex pipe through Pipelex's runtime bridge.
- Mistral Workflows — on its Temporal foundation — gives durability, automatic retries, streaming progress, and observability; Pipelex runs the AI method.

!!! info "Both backends are Temporal underneath"
    Pipelex on Mistral Workflows and [Pipelex on Temporal](../temporal/index.md) are the same durability primitive packaged two ways. The difference is *who runs the control plane*: here it's Mistral's managed Workflows service; there it's a Temporal deployment you operate yourself. See [Choosing a Backend](choosing-a-backend.md).

## What you get

- **Durable execution** — pipe runs survive worker restarts and transient failures, resuming from history.
- **Automatic retries** — what retries depends on the orchestration mode: in `direct` mode the whole pipe runs inside one host activity that retries as a unit; in `mistralai-workflows` mode each leaf operator (LLM call, extraction, image generation) runs as its own host activity and retries independently. See [Orchestration & Delivery](execution-modes.md).
- **Streaming progress** — surface live pipe progress through the Workflows Task event API. See [Streaming Progress](streaming.md).
- **The same methods, unchanged** — your `.mthds` bundles don't change between local, Temporal, and Mistral Workflows execution.

## Next steps

- **[Installation & Preview Status](installation.md)** — install the preview package and its prerequisites.
- **[Your First Pipelex Workflow](your-first-pipelex-workflow.md)** — register a Pipelex activity and run a pipe end to end.
- **[Orchestration & Delivery](execution-modes.md)** — how a pipe runs inside an activity, and what each mode requires.
- **[Choosing a Backend](choosing-a-backend.md)** — Mistral Workflows vs your own Temporal cluster.
