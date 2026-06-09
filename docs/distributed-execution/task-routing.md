---
title: "Task-Queue Routing"
description: "Route Pipelex activities to specific Temporal task queues with per-activity, per-handle precision. Layer per-queue and per-handle timeout, retry, and rate overrides on top."
---

# Task-Queue Routing

When one task queue isn't enough, Pipelex routes each activity to a specific queue based on the activity name and (optionally) the runtime handle — the model id, image-gen handle, or extract handle the activity is about to call. On top of routing, each queue and each handle can carry its own timeouts, retry policies, and rate caps.

This page is the reference for the three composable layers: per-activity routing, per-queue overlays, per-handle overlays. If you're running a single worker on a single queue, you can skip this page entirely.

---

## Why you'd route

Three motivations cover almost every real-world case:

- **Provider isolation** — OpenAI and Anthropic have independent rate limits, retry semantics, and outage windows. Routing each provider's LLM calls to its own pool means one provider's incident doesn't drain the other's throughput.
- **Activity-class isolation** — A long-running OCR call shouldn't share a worker pool with thousands of short LLM calls. Routing extract activities to a dedicated `extract_q` keeps slow work from starving the rest.
- **Handle-specific tuning** — One specific model (say, a long-context Claude variant with 60-second timeouts) needs a different retry and timeout policy than the rest of the Anthropic pool. Per-handle overlays let you tune one model without forking the whole queue.

---

## Per-activity, per-handle routing

Routing lives under `[temporal.worker_config.activity_queues.<activity_name>]`. Each entry declares a `default` queue and an optional `by_handle` map keyed by the activity's routing key:

```toml
[temporal.worker_config.activity_queues.act_llm_gen_text]
default = "openai_q"
by_handle.anthropic-default = "anthropic_q"
by_handle.gemini-pro = "gemini_q"

[temporal.worker_config.activity_queues.act_llm_gen_object]
default = "openai_q"
by_handle.anthropic-default = "anthropic_q"

[temporal.worker_config.activity_queues.act_img_gen_images]
default = "imggen_q"

[temporal.worker_config.activity_queues.act_extract_gen_extract_pages]
default = "extract_q"
```

The **routing key** is the runtime handle the activity is about to call:

| Activity                          | Routing key            | Source                          |
|-----------------------------------|------------------------|---------------------------------|
| `act_llm_gen_text`                | LLM model handle       | The `llm_handle` on the call    |
| `act_llm_gen_object`              | LLM model handle       | The `llm_handle` on the call    |
| `act_llm_gen_object_list`         | LLM model handle       | The `llm_handle` on the call    |
| `act_img_gen_images`              | `img_gen_handle`       | The image generation backend    |
| `act_extract_gen_extract_pages`   | `extract_handle`       | The OCR / extract backend       |
| `act_search_gen_sourced_answer`   | `search_handle`        | The web search backend          |
| `act_search_gen_structured`       | `search_handle`        | The web search backend          |
| `act_jinja2_gen_text`             | (none — pass `None`)   | Template rendering has no handle |
| `act_render_page_views`           | (none — pass `None`)   | Page-view rendering has no handle |

`WorkerConfig.resolve_queue(activity_name, routing_key)` walks three layers, returning the first match:

1. `worker_config.activity_queues[activity_name].by_handle[routing_key]`
2. `worker_config.activity_queues[activity_name].default`
3. `default_task_queue` (worker-wide fallback)

When `activity_queues` is completely empty (the shipping default), `resolve_queue` returns `None` and dispatch omits the `task_queue` kwarg — every activity rides the workflow's own queue, preserving single-queue behavior for installs that haven't opted into routing.

!!! note "Every routed queue needs a `queue_options` entry"

    Any queue named under `[temporal.worker_config.activity_queues.*]` must have a matching `[temporal.queue_options.<q>]` entry (an empty stanza is fine and means "use worker-config baselines for this queue"). Routing to an undeclared queue is treated as a typo and fails at config-load with `TemporalConfigError`. `default_task_queue` is the one implicit exception — it never needs its own `queue_options` entry.

---

## Per-queue option overlays

Each queue can carry its own timeouts, retry policy, and cluster-wide rate cap under `[temporal.queue_options.<queue>]`:

```toml
[temporal.queue_options.openai_q]
start_to_close_timeout = "0:05:00"
heartbeat_timeout = "0:01:00"
max_task_queue_activities_per_second = 500

[temporal.queue_options.openai_q.retry_policy_config]
initial_interval = "0:00:01"
maximum_attempts = 4
non_retryable_error_types_extra = ["OpenAIBadRequestError"]

[temporal.queue_options.anthropic_q]
start_to_close_timeout = "0:10:00"
max_task_queue_activities_per_second = 50

[temporal.queue_options.extract_q]
start_to_close_timeout = "0:30:00"
heartbeat_timeout = "0:05:00"

# Empty stanzas for queues routed in activity_queues that don't need any
# tuning — required by the orphan-queue validator at config-load.
[temporal.queue_options.gemini_q]
[temporal.queue_options.imggen_q]
```

All fields are optional — anything you leave out falls through to the worker-config baseline:

| Field                                       | Type        | When unset                                  |
|---------------------------------------------|-------------|---------------------------------------------|
| `start_to_close_timeout`                    | duration    | Use `default_activity_start_to_close_timeout` |
| `schedule_to_close_timeout`                 | duration    | Omitted; SDK applies its default            |
| `schedule_to_start_timeout`                 | duration    | Omitted; SDK applies its default            |
| `heartbeat_timeout`                         | duration    | Use `default_activity_heartbeat_timeout`    |
| `retry_policy_config`                       | overlay     | Use worker-config `retry_policy_config`     |
| `max_task_queue_activities_per_second`      | float       | No cluster-wide cap on this queue           |

`max_task_queue_activities_per_second` is the **cluster-wide** rate cap on the queue — every worker on the queue sends this value to the Temporal server; the latest writer wins. Before this config knob existed, Pipelex hard-coded `1000` on every worker. The shipped default keeps the cap at `1000` for the default queue:

```toml
[temporal.queue_options.temporal_task_queue]
max_task_queue_activities_per_second = 1000
```

Deployments using non-default queue names should add their own `[temporal.queue_options.<queue>]` entries with the cap appropriate for that backend pool.

---

## Per-handle option overlays

For the rare case where one model variant needs different timeouts or retry from its queue baseline, declare a `handle_options.<handle>` entry on the activity route:

```toml
[temporal.worker_config.activity_queues.act_llm_gen_text]
default = "openai_q"
by_handle.anthropic-default = "anthropic_q"
by_handle.anthropic-claude-3-5-sonnet-long-context = "anthropic_q"

[temporal.worker_config.activity_queues.act_llm_gen_text.handle_options.anthropic-claude-3-5-sonnet-long-context]
start_to_close_timeout = "0:30:00"

[temporal.worker_config.activity_queues.act_llm_gen_text.handle_options.anthropic-claude-3-5-sonnet-long-context.retry_policy_config]
maximum_attempts = 2
non_retryable_error_types_extra = ["AnthropicLongContextOverflow"]
```

Handle overlays deliberately cover only timeout and retry. Heartbeat cadence is a property of the backend, not the model, so it lives on the queue overlay. Add a field to `HandleOptions` only when a real case requires it.

### Resolution order

At dispatch time, `WorkerConfig.resolve_dispatch(activity_name, routing_key)` composes the three layers in last-wins order for each scalar:

1. **Baseline** — worker-config defaults (`default_activity_start_to_close_timeout`, `default_activity_heartbeat_timeout`, `retry_policy_config`).
2. **Queue overlay** — `queue_options[resolved_queue]` if it exists.
3. **Handle overlay** — `worker_config.activity_queues[activity_name].handle_options[routing_key]` if it exists.

Each layer can replace a scalar (timeout, retry interval, max attempts) or leave it untouched. The result is splatted directly into `workflow.execute_activity(...)`.

`non_retryable_error_types` is the one exception to last-wins: it **composes additively** across layers. The baseline declares a main list; each overlay can declare `non_retryable_error_types_extra` to add more entries. Removing entries via overlay is deliberately not supported — per-queue and per-handle layers can only add to the no-retry list. This is a safety lean: it's easier to say "never retry this" than to undo it by accident at a narrower scope.

The `RetryPolicyConfig` schema is split into a baseline class (owns `non_retryable_error_types`) and an overlay class (owns `non_retryable_error_types_extra`). `extra = "forbid"` rejects the wrong field at each layer so the additive rule is enforced at config load.

---

## Tracing the resolution

When timeouts or retries behave unexpectedly, turn on dispatch resolution tracing:

```toml
[temporal.temporal_config.temporal_log_config]
is_dispatch_resolution_traced = true
```

Every `workflow.execute_activity` call then emits one INFO log line with the resolved queue, the resolved `start_to_close_timeout`, the resolved retry attempts, and — most useful — **which layer each scalar came from** (`baseline`, `queue_options`, or `handle_options`). This is verbose, so leave it off by default; turn it on when you're hunting a misconfigured overlay.

---

## What's next

- **[Worker Deployment](workers.md)** — pair routing with `--scope` so each worker pool only registers the activities it should receive.
- **[Workflow Observability](observability.md)** — see what the dashboard shows for each routed activity.
