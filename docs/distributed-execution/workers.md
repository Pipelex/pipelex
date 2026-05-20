---
title: "Worker Deployment"
description: "Run and tune Pipelex Temporal worker processes — the `pipelex worker` CLI, default task queue, worker scopes, and named runtime profiles."
---

# Worker Deployment

A worker process polls one Temporal task queue for workflows and activities, executes them, and reports results. This page covers how to run a worker, how to scope it to a subset of work, and how to tune its concurrency.

For the cluster-side prerequisites that must be in place before a worker can boot, see [Cluster Setup](cluster-setup.md).

---

## Running a worker

The simplest invocation reads everything from `pipelex.toml`:

```bash
pipelex worker
```

This boots a worker that polls `[temporal.worker_config].default_task_queue`, uses the `[temporal.worker_scopes].default_scope` worker scope, and applies the `[temporal.worker_runtime_profiles].default_profile` runtime profile. For a single-machine deployment that's all you need.

Available flags:

| Flag             | Purpose                                                                          |
|------------------|----------------------------------------------------------------------------------|
| `--task-queue`   | Override the polled queue. Must be a known queue (see strict validation below).  |
| `--scope`        | Pick a worker scope from `[temporal.worker_scopes.scopes]`.                      |
| `--profile`      | Pick a runtime profile from `[temporal.worker_runtime_profiles.profiles]`.       |
| `--no-sandbox`   | Run workflows without Temporal's sandbox restrictions. For tests / debugging.    |
| `--unit-testing` | Run in unit-testing mode (sets `RunMode.UNIT_TEST`).                             |

Example:

```bash
pipelex worker --task-queue anthropic_q --scope runner-llm --profile anthropic-tier4
```

---

## The default task queue

```toml
[temporal.worker_config]
default_task_queue = "temporal_task_queue"
```

`default_task_queue` is the queue a worker polls when no `--task-queue` flag is passed. It's also the fallback used when [Task-Queue Routing](task-routing.md) is configured but a given activity has no specific routing entry.

The key was previously named `task_queue`; the migration map in `pipelex.toml` rewrites legacy configs on load, so existing deployments keep working without manual edits.

---

## Strict `--task-queue` validation

`pipelex worker --task-queue <q>` fast-fails with `WorkerTaskQueueUnknownError` when `<q>` is not declared anywhere in the Temporal config — not in `default_task_queue`, not in any `[temporal.activity_queues.<activity>]` entry, and not in any `[temporal.queue_options.<queue>]` overlay. The error message includes a Levenshtein "Did you mean?" suggestion when a close match exists.

This catches operator typos in seconds rather than after a multi-second library boot. Programmatic callers (tests, library code) get the same check inside `TemporalTaskManager.run_worker`.

---

## Worker scopes

A worker scope picks which workflows and activities a worker process registers with Temporal. Scopes are declared under `[temporal.worker_scopes.scopes.<name>]` and selected via `--scope <name>`.

Built-in scopes:

| Scope             | Workflows | Activities                                          | Use case                                                                  |
|-------------------|-----------|-----------------------------------------------------|---------------------------------------------------------------------------|
| `full`            | All       | All                                                 | Single-worker deployment. Default.                                        |
| `router`          | All       | None                                                | Workflow-only worker. Pair with `runner` to force cross-process dispatch. |
| `runner`          | None      | All                                                 | Activity-only worker. Counterpart to `router`.                            |
| `runner-llm`      | None      | `act_llm_gen_text`, `act_llm_gen_object`, `act_llm_gen_object_list` | One pool dedicated to LLM calls.                                          |
| `runner-img-gen`  | None      | `act_img_gen_images`, `act_render_page_views`       | One pool dedicated to image generation.                                   |
| `runner-extract`  | None      | `act_extract_gen_extract_pages`, `act_render_page_views` | One pool dedicated to OCR / document extraction.                          |
| `runner-jinja2`   | None      | `act_jinja2_gen_text`                               | One pool dedicated to template rendering (rare; usually fine in-band).    |

`act_render_page_views` is intentionally registered under **both** `runner-img-gen` and `runner-extract` so neither pool breaks when the activity is routed to either. The `runner-llm` scope splits all three LLM activity types (text, object, object-list) onto the same pool — they share the same provider connections so splitting further would only add operational overhead.

The `full` scope is the right default for almost every deployment. Reach for `router`/`runner` splits when you need to enforce cross-worker execution boundaries (durability under partial failure, deterministic activity placement) or when one activity class has very different resource needs from the rest.

---

## Worker runtime profiles

A runtime profile bundles the worker's concurrency knobs: how many workflow tasks it polls in parallel, how many activities it runs concurrently, how aggressively it heartbeats, and how long it waits during graceful shutdown.

The default profile is shipped in `pipelex.toml`:

```toml
[temporal.worker_runtime_profiles]
default_profile = "default"

[temporal.worker_runtime_profiles.profiles.default]
tuning_mode = "explicit"
max_cached_workflows = 10000
max_concurrent_workflow_tasks = 1000
max_concurrent_activities = 1000
max_concurrent_local_activities = 1000
max_concurrent_workflow_task_polls = 100
max_concurrent_activity_task_polls = 100
max_activities_per_second = 1000
sticky_queue_schedule_to_start_timeout = "0:30:00"
max_heartbeat_throttle_interval = "1:00:00"
default_heartbeat_throttle_interval = "1:00:00"
graceful_shutdown_timeout = "0:30:00"
```

Add a custom profile when one worker pool needs different tuning from another — for example, an LLM pool tied to a tier-4 provider quota:

```toml
[temporal.worker_runtime_profiles.profiles.anthropic-tier4]
tuning_mode = "explicit"
max_cached_workflows = 0
max_concurrent_workflow_tasks = 1
max_concurrent_activities = 50
max_concurrent_local_activities = 50
max_concurrent_workflow_task_polls = 1
max_concurrent_activity_task_polls = 50
max_activities_per_second = 8
sticky_queue_schedule_to_start_timeout = "0:30:00"
max_heartbeat_throttle_interval = "1:00:00"
default_heartbeat_throttle_interval = "1:00:00"
graceful_shutdown_timeout = "0:30:00"
```

Select it on the worker process:

```bash
pipelex worker --profile anthropic-tier4
```

`tuning_mode` must be `"explicit"` in this release. A `"resource_based"` value is reserved but not implemented yet — the config validator rejects it with a clear message.

---

## Putting it together

A common production topology splits workers along three lines:

- One **router** worker pool that owns workflow orchestration and dispatches activities back out to specialized runner pools.
- One **LLM runner** pool per provider quota — separating OpenAI and Anthropic lets each scale independently.
- One **image-gen runner** pool that owns image generation activities (and their occasional page-view rendering side effects).

The corresponding `pipelex.toml` adds two profiles plus the routing config (see [Task-Queue Routing](task-routing.md) for the routing details):

```toml
[temporal.worker_config]
default_task_queue = "temporal_task_queue"

[temporal.activity_queues.act_llm_gen_text]
default = "openai_q"
by_handle.anthropic-default = "anthropic_q"

[temporal.activity_queues.act_img_gen_images]
default = "imggen_q"

[temporal.worker_runtime_profiles.profiles.openai-pool]
# ... explicit tuning for the OpenAI pool ...

[temporal.worker_runtime_profiles.profiles.anthropic-tier4]
# ... explicit tuning for the Anthropic pool ...
```

Boot four workers — typically one process each, on its own machine or container:

```bash
# Router: orchestrates workflows, no activity execution
pipelex worker --scope router --task-queue temporal_task_queue

# OpenAI LLM pool
pipelex worker --scope runner-llm --task-queue openai_q --profile openai-pool

# Anthropic LLM pool
pipelex worker --scope runner-llm --task-queue anthropic_q --profile anthropic-tier4

# Image generation pool
pipelex worker --scope runner-img-gen --task-queue imggen_q
```

The router worker hosts every workflow; each runner worker hosts only the activities its scope declares; routing decides which runner pool receives each activity at dispatch time.

---

## What's next

- **[Task-Queue Routing](task-routing.md)** — route specific activities to specific worker pools with per-activity / per-handle precision, then layer per-queue timeouts and retry policies on top.
- **[Workflow Observability](observability.md)** — what each worker writes to the Temporal Web UI: workflow ids, activity summaries, search-attribute filters.
