---
title: "Your First Pipelex Workflow on Mistral Workflows"
description: "Register a Pipelex activity on a Mistral Workflows worker, call it from a workflow, and run it — the preview end-to-end path."
---

# Your First Pipelex Workflow

!!! warning "Preview"
    This walkthrough targets the preview `pipelex-mistralai-workflows` package. The Pipelex bridge calls shown here (`run_pipe_via_bridge`, `PipelexPipeRunInput`) are part of Pipelex core and stable; anything specific to the plugin package is flagged inline.

We'll register an activity that runs a Pipelex pipe, call it from a Mistral Workflow, and execute the whole thing on a worker.

## Prerequisites

- The preview package installed — see [Installation & Preview Status](installation.md).
- A working Mistral Workflows setup (workspace, API key, `.env`) per Mistral's own first-workflow guide.
- A Pipelex method available on your `PIPELEXPATH` (or passed as a library crate — see [Execution Modes](execution-modes.md)). The example below assumes a pipe named `answer_question`.

## Step 1 — Define a worker that runs a Pipelex pipe

Pipelex exposes a small, JSON-in / JSON-out entry point — `run_pipe_via_bridge(PipelexPipeRunInput(...))` — designed to be called from inside any host-runtime activity. The cleanest first integration is to write your own activity that calls it. Every symbol here is part of Pipelex core.

Create `my_pipelex_worker.py`:

```python
import mistralai.workflows as workflows

from pipelex.runtime_bridge.bridge import PipelexPipeRunInput, run_pipe_via_bridge


@workflows.activity()
async def run_pipelex_pipe(pipe_code: str, inputs: dict) -> dict:
    """Run a Pipelex pipe inside a Mistral Workflows activity.

    The bridge boots Pipelex on first call (idempotent), runs the pipe, and
    returns a JSON-safe result. Only JSON crosses the activity boundary — no
    Pipelex internal objects.
    """
    output = await run_pipe_via_bridge(
        PipelexPipeRunInput(pipe_code=pipe_code, inputs=inputs)
    )
    return output.model_dump()


@workflows.workflow.define(name="pipelex_example_workflow")
class PipelexExampleWorkflow:
    @workflows.workflow.entrypoint
    async def run(self, pipe_code: str, inputs: dict) -> dict:
        return await run_pipelex_pipe(pipe_code, inputs)


async def main() -> None:
    await workflows.run_worker([PipelexExampleWorkflow])


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
```

!!! note "Illustrative: ready-made activity"
    The plugin package may also ship a ready-to-register Pipelex activity so you can add it to a worker without writing the wrapper yourself. Its exact name and registration signature are still settling in preview — confirm them against the installed package. Writing your own `@workflows.activity()` around `run_pipe_via_bridge`, as above, works today and is the safest starting point.

## Step 2 — Run the worker

```bash
uv run python my_pipelex_worker.py
```

The worker connects to the Mistral API and registers `pipelex_example_workflow`. You should see it in the [Mistral Console](https://console.mistral.ai/build/workflows).

## Step 3 — Trigger execution

From the Console, select `pipelex_example_workflow`, click **Start Workflow**, and pass input such as:

```json
{ "pipe_code": "answer_question", "inputs": { "question": "What is MTHDS?" } }
```

You can also start it programmatically with the Mistral SDK via `client.workflows.*`.

<!-- ILLUSTRATIVE: the exact client.workflows.* call shape is generic Mistral Workflows usage, not Pipelex-specific. Confirm against the Mistral SDK docs. -->

## What just happened

- The activity called `run_pipe_via_bridge`, which **booted Pipelex on first call** (idempotent — subsequent activities reuse the running instance).
- With no `execution_mode` set, the pipe ran in **`direct`** mode: in-process inside the activity, blocking until it completed.
- The bridge returned a `PipelexPipeRunOutput` — `output_dict`, `main_stuff_name`, `pipeline_run_id`, `is_completed`, and more — which the activity serialized with `model_dump()`.
- The boundary is **JSON-only**: no Pipelex internal types (`PipeJob`, `WorkingMemory`, `PipeOutput`) cross the activity edge, which is what keeps the pipe replayable and the activity serializable.

## Next

- **[Execution Modes](execution-modes.md)** — run the pipe in-process, delegate to your own Temporal workers, or fire-and-forget.
- **[Streaming Progress](streaming.md)** — surface live progress as the pipe runs.
