---
title: "Pipelex on Temporal"
description: "Run Pipelex pipelines as durable Temporal workflows on your own Temporal cluster or Temporal Cloud. Cluster setup, worker deployment, task-queue routing, and dashboard observability."
---

# Pipelex on Temporal

Run your Pipelex pipelines as durable Temporal workflows across one or more worker processes. This section walks through setting up the cluster, running workers, routing work to the right pools, and reading the Temporal Web UI.

This is the Temporal backend for distributed execution: you run **Pipelex's own Temporal workers** against a Temporal cluster you operate (self-hosted or Temporal Cloud) — you own the control plane. A second, managed alternative (Pipelex on Mistral Workflows) is coming soon. See the [Distributed Execution overview](../index.md) for the big picture.

## What it is

Pipelex pipelines normally run in-process — you call `pipelex run pipe ...` or invoke a pipe from Python and everything happens in one Python process. With the optional `pipelex-temporal` integration, the same pipelines run as **Temporal workflows**: each pipe execution becomes a workflow on a Temporal cluster, child pipes become child workflows, and every LLM call, image generation, or document extraction becomes a Temporal activity executed on a worker. Temporal handles durability, retries, scheduling, and visibility; Pipelex handles the AI work.

The whole layer is opt-in. Flip `[temporal] is_enabled = true` in `.pipelex/pipelex.toml`, install `pipelex-temporal`, and the same `.mthds` methods run distributed without changing a line.

## When you'd want it

You don't need Temporal for local development — pipes run in-process by default. Reach for distributed execution when you need:

- **Durability** — long-running pipelines survive process restarts and worker crashes. Temporal replays history to resume exactly where execution left off.
- **Retries with budget control** — every activity (LLM call, extract, image gen) retries independently with per-activity timeouts and retry policies.
- **Horizontal scale** — fan out work across multiple worker machines. Pipelex lets you route OpenAI calls to one pool, Anthropic to another, OCR to a third.
- **Operational visibility** — every workflow shows up in the Temporal Web UI with the pipe code, pipeline run id, user, session, and a per-activity summary line.

## The big picture

```
Your application
      │
      │  pipe_run(...)  ──→  starts a Temporal workflow
      ▼
┌────────────────────┐
│   Temporal cluster │  durability, history, retries, search
└─────────┬──────────┘
          │  tasks distributed by queue
          ▼
   ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
   │   worker    │ │   worker    │ │   worker    │  poll task queues,
   │  (router)   │ │ (LLM pool)  │ │ (img-gen)   │  execute workflows
   └─────────────┘ └─────────────┘ └─────────────┘  and activities
```

A submitter (your app or `pipelex run`) starts a workflow; one or more worker processes poll task queues for work; results flow back through the workflow's history. You can run a single worker that handles everything, or split workers by activity class for independent scaling and isolation.

## What you'll set up

Three things, in this order:

- **[Cluster Setup](../cluster-setup.md)** — one-time namespace prerequisites: register the custom search attributes Pipelex needs for the dashboard view. Run `pipelex-temporal setup-namespace` and you're done.
- **[Worker Deployment](../workers.md)** — how to run `pipelex-temporal worker`, what `--scope` and `--profile` do, and how to compose multiple workers into a deployment.
- **[Task-Queue Routing](../task-routing.md)** — when you outgrow a single queue: per-activity routing, per-queue timeouts and retry policies, per-handle overrides. Skip on day one; revisit when you need to isolate workloads.

## What you'll see in the Temporal dashboard

Every workflow Pipelex starts carries human-readable identity: a workflow id derived from your pipeline run id, a Markdown summary of the pipe and its inputs, and per-activity summary lines that explain what each LLM or extract call is doing. Filter by `PipeCode`, `PipelineRunId`, `UserId`, `SessionId`, or `DomainCode` from the dashboard's search attribute selector. See **[Workflow Observability](../observability.md)** for the full reference.

## Quick start

Minimal configuration in `.pipelex/pipelex.toml`:

```toml
[temporal]
is_enabled = true

[temporal.worker_config]
default_task_queue = "temporal_task_queue"

[temporal.temporal_config]
selected_server = "local"

[temporal.temporal_config.temporal_server_configs.local]
target_host = "localhost:7233"
namespace = "default"
api_key_method = "none"
```

Register the custom search attributes once (assumes Temporal is reachable):

```bash
pipelex-temporal setup-namespace
```

Boot a worker against the default task queue:

```bash
pipelex-temporal worker
```

Submit work from your application — the same `pipe_run(...)` you'd use locally now executes as a Temporal workflow because `[temporal] is_enabled = true`. The Pipelex Python API automatically dispatches through the Temporal hub.

## Where to go next

- **[Cluster Setup](../cluster-setup.md)** — search attributes, `pipelex-temporal setup-namespace`, Temporal Cloud permission model.
- **[Worker Deployment](../workers.md)** — `pipelex-temporal worker`, scopes, runtime profiles, multi-worker topologies.
- **[Task-Queue Routing](../task-routing.md)** — `activity_queues`, queue options, per-handle overrides, dispatch tracing.
- **[Workflow Observability](../observability.md)** — workflow ids, activity ids, summary fields, search-attribute filtering.

For the runtime mechanics that make distributed execution work under the hood — LibraryCrate propagation, deferred hydration, per-workflow class registry isolation — see [Temporal Integration](../../under-the-hood/temporal-integration.md) and [Distributed Content Generation](../../under-the-hood/distributed-content-generation.md).
