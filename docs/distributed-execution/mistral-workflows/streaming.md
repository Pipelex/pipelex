---
title: "Streaming Progress"
description: "Surface live Pipelex pipe progress through Mistral Workflows' Task event API — one event per activity, or per-step updates in DIRECT mode."
---

# Streaming Progress

!!! warning "Preview"
    Streaming integration ships in the preview `pipelex-mistralai-workflows` package. The Mistral Workflows streaming primitives shown here are stable; the Pipelex-specific entry points are flagged inline.

Mistral Workflows publishes real-time events from activities through its **Task** API, which powers live UIs and progress indicators. A Pipelex activity wraps a pipe run in a Task and emits progress as the pipe executes.

## How streaming works

Inside an activity you open a `Task` and push state updates as work proceeds:

```python
from mistralai.workflows.core.task import Task

async with Task(type="pipelex_progress", state={"completed_steps": []}) as task:
    # ... run the pipe, updating task.state as steps complete ...
    await task.update_state({"completed_steps": task.state["completed_steps"] + ["answer_question"]})
```

Mistral Workflows wraps each update with workflow/activity context and publishes it over NATS for consumers to subscribe to.

## Two granularities

The Pipelex integration surfaces progress at one of two levels:

- **Per-activity** — a single Task per pipe run: started, in-progress, completed (or failed). This is the cheapest option and works regardless of execution mode.
- **Per-step (`DIRECT` mode)** — driven by Pipelex's own execution-trace events, the activity emits a Task update for each pipe step as it starts and finishes, exposing started-steps, completed-steps, and the current pipe code. Because it rides on in-process trace events, per-step granularity applies to `DIRECT` execution; Temporal modes keep the single started/finished pair.

<!-- ILLUSTRATIVE: the package's streaming entry-point names and the exact per-step task `type`/state schema are still settling in preview; the per-activity vs per-step distinction is the design-locked behavior. Confirm symbols against the installed package. -->

## Consuming events

Subscribe to the published events with the Mistral Workflows client's event-streaming APIs — see Mistral's "Consuming Streaming Events" guide. This guide doesn't duplicate the consumer side; the events a Pipelex activity emits are ordinary Workflows Task events.

!!! note "Payload limit"
    NATS messages are capped at **1 MB**. Stream small progress state — step names, counts, a current pipe code — not large pipe outputs. For large results, store them externally (or use the bridge's delivery assignment) and stream a reference.
