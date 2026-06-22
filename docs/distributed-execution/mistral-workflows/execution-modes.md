---
title: "Orchestration & Delivery"
description: "How a Pipelex pipe runs inside a Mistral Workflows activity — the orchestration-mode token that picks the backend and the delivery axis that picks the wait-semantics — and what each requires."
---

# Orchestration & Delivery

When you run a pipe through the bridge, two orthogonal fields on the input decide *how* it runs:

- **`orchestration_mode`** — *which* orchestrator runs the pipe. An **open string token**: core ships only `direct` (in-process); each backend plugin contributes its own token. The same activity code can run a pipe in-process, hand it off to your own Temporal workers, or decompose it into native Mistral Workflows primitives — just by changing this token.
- **`delivery`** — *whether the call waits*. `blocking` (await completion, the default) or `fire_and_forget` (return immediately with a `workflow_id`; completion is signalled out-of-band).

## The runtime bridge

Pipes are invoked through `run_pipe_via_bridge`, which takes a `PipelexPipeRunInput` and returns a `PipelexPipeRunOutput`. Both are plain JSON-safe models — the boundary never carries Pipelex internal types. The bridge boots Pipelex on first call, validates the input, optionally opens a per-call scoped library from a crate, then dispatches on `orchestration_mode`, passing `delivery` to the resolved orchestrator.

## Orchestration tokens

| Token | What it does | Requires |
|-------|--------------|----------|
| `direct` | Runs the pipe in-process, inside the calling activity. Fastest feedback, simplest ops. The default. Always blocks (in-process has no async path). | Pipelex core |
| `temporal` | Dispatches the pipe as a Pipelex Temporal workflow, running durably on your own Temporal worker fleet. Honors both delivery modes: `blocking` awaits completion, `fire_and_forget` returns the `workflow_id` immediately. | `pipelex-temporal` |
| `mistralai-workflows` | Decomposes the pipe into native Mistral Workflows primitives — controllers as child workflows, leaf operators as activities — surfacing per-step retry, signals, and cancellation through the host runtime. | `pipelex-mistralai-workflows` |

The token values above are the literal strings you set on the `orchestration_mode` field. The set is **open** — a backend plugin registers its own token, so there is no closed enum to match against; an unregistered token is refused at dispatch (see below).

For local and most in-activity use, `direct` is the right default: the pipe simply runs where the activity runs, and Mistral Workflows provides the durability and retry around the activity as a whole.

## The delivery axis

`delivery` is independent of the backend:

- `blocking` (default) — the bridge awaits the pipe to completion and returns its full output.
- `fire_and_forget` — the bridge returns immediately with the `workflow_id`; completion is delivered out-of-band via a delivery assignment (webhook / storage). Only a backend that can do genuine async honors this; `direct` always blocks regardless. A `fire_and_forget` call **requires** a `delivery_assignment_dump` with at least one target, or it is rejected up front so a completion is never silently dropped.

## Input fields that matter

`PipelexPipeRunInput` carries everything the bridge needs:

- `pipe_code` — the pipe to run.
- `inputs` — the pipe's inputs, as a JSON dict.
- `output_name` — optional override for the output variable name.
- `pipeline_run_id`, `user_id` — identity carried into tracing and observability.
- `orchestration_mode` — the backend token (defaults to `direct`).
- `delivery` — `blocking` (default) or `fire_and_forget`.
- `library_crate_dump` — an optional serialized library snapshot. Use it when the pipe isn't already loaded at boot: the bridge opens a per-call scoped library from the crate, runs the pipe, and tears it down afterward. This is the dump-based library transport that lets a worker run methods it didn't load at startup.
- `delivery_assignment_dump` — required when `delivery` is `fire_and_forget`; describes where to deliver the result (webhook / storage).

## Missing-dependency behavior

The bridge fails loudly and helpfully:

- Requesting a token with no registered orchestrator (its plugin isn't installed) raises `MissingOrchestratorError` — *"No orchestrator is registered for orchestration mode '{token}'; is its plugin installed?"*. The message names the token but no plugin — installing the backend distribution (`pipelex-temporal`, `pipelex-mistralai-workflows`, …) makes its token available.
- Requesting `fire_and_forget` without a `delivery_assignment_dump` is rejected up front, so a completion is never silently dropped.

!!! warning "`mistralai-workflows` is preview"
    The dispatch hook for the `mistralai-workflows` token lives in Pipelex core, but the implementation that decomposes a pipe into native Workflows primitives ships in the preview `pipelex-mistralai-workflows` package. Treat end-to-end `mistralai-workflows` as preview and verify behavior against the installed package. For most integrations, running pipes in `direct` mode inside your own activity already gives you durable, retryable execution from Mistral Workflows.
