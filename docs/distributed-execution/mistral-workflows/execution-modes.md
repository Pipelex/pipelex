---
title: "Execution Modes"
description: "How a Pipelex pipe runs inside a Mistral Workflows activity — DIRECT, TEMPORAL_BLOCKING, TEMPORAL_FIRE_AND_FORGET, and MISTRAL_NATIVE — and what each requires."
---

# Execution Modes

When you run a pipe through the bridge, the `execution_mode` field on the input selects *how* that pipe runs. The same activity code can run a pipe in-process, hand it off to your own Temporal workers, or decompose it into native Mistral Workflows primitives.

## The runtime bridge

Pipes are invoked through `run_pipe_via_bridge`, which takes a `PipelexPipeRunInput` and returns a `PipelexPipeRunOutput`. Both are plain JSON-safe models — the boundary never carries Pipelex internal types. The bridge boots Pipelex on first call, validates the input, optionally opens a per-call scoped library from a crate, then dispatches on `execution_mode`.

## The modes

| Mode | What it does | Requires |
|------|--------------|----------|
| `DIRECT` | Runs the pipe in-process, inside the calling activity, blocking until it completes. Fastest feedback, simplest ops. The default. | Pipelex core |
| `TEMPORAL_BLOCKING` | Dispatches the pipe as a Pipelex Temporal workflow and awaits completion. The pipe runs durably on your own Temporal worker fleet. | `pipelex[temporal]` |
| `TEMPORAL_FIRE_AND_FORGET` | Dispatches the pipe as a Pipelex Temporal workflow and returns immediately with the `workflow_id`. Completion is signalled out-of-band via a delivery assignment (webhook / storage). | `pipelex[temporal]`, and `delivery_assignment_dump` |
| `MISTRAL_NATIVE` | Decomposes the pipe into native Mistral Workflows primitives — controllers as child workflows, leaf operators as activities — surfacing per-step retry, signals, and cancellation through the host runtime. | `pipelex-mistralai-workflows` |

For local and most in-activity use, `DIRECT` is the right default: the pipe simply runs where the activity runs, and Mistral Workflows provides the durability and retry around the activity as a whole.

## Input fields that matter

`PipelexPipeRunInput` carries everything the bridge needs:

- `pipe_code` — the pipe to run.
- `inputs` — the pipe's inputs, as a JSON dict.
- `output_name` — optional override for the output variable name.
- `pipeline_run_id`, `user_id` — identity carried into tracing and observability.
- `execution_mode` — one of the modes above (defaults to `DIRECT`).
- `library_crate_dump` — an optional serialized library snapshot. Use it when the pipe isn't already loaded at boot: the bridge opens a per-call scoped library from the crate, runs the pipe, and tears it down afterward. This is the dump-based library transport that lets a worker run methods it didn't load at startup.
- `delivery_assignment_dump` — required for `TEMPORAL_FIRE_AND_FORGET`; describes where to deliver the result (webhook / storage).

## Missing-dependency behavior

The bridge fails loudly and helpfully when a mode's dependency isn't installed:

- Requesting a `TEMPORAL_*` mode without the extra raises `MissingPipelexTemporalExtraError` — *"Install with: pip install 'pipelex[temporal]'"*.
- Requesting `MISTRAL_NATIVE` without the plugin raises `MissingMistralWorkflowsPluginError` — *"Install with: pip install pipelex-mistralai-workflows"*.
- Requesting `TEMPORAL_FIRE_AND_FORGET` without a `delivery_assignment_dump` is rejected up front, so a completion is never silently dropped.

!!! warning "MISTRAL_NATIVE is preview"
    The dispatch hook for `MISTRAL_NATIVE` lives in Pipelex core, but the implementation that decomposes a pipe into native Workflows primitives ships in the preview `pipelex-mistralai-workflows` package. Treat end-to-end `MISTRAL_NATIVE` as preview and verify behavior against the installed package. For most integrations, running pipes in `DIRECT` mode inside your own activity already gives you durable, retryable execution from Mistral Workflows.
