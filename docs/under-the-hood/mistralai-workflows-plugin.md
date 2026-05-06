---
title: "Mistral Workflows Plugin"
description: "Run Pipelex pipes from inside Mistral Workflows activities — install, execution modes, and when to pick which."
---

# Mistral Workflows Plugin

The `pipelex.plugins.mistralai_workflows` plugin lets you call Pipelex pipes from inside [Mistral Workflows](https://docs.mistral.ai/) activities. Pipelex remains in charge of pipe orchestration; Mistral Workflows owns the surrounding activity, retry policy, scheduling, and (optionally) durable execution.

For worked examples (Tier 1 pre-decorated activity, Tier 2 helper-in-your-own-activity, Tier 3 full control with `library_crate_dump`), see the [Recipes](./mistralai-workflows-recipes.md) page.

---

## Install

The `mistralai-workflows` dependency is **strictly optional**. Install it as an extra:

```bash
pip install 'pipelex[mistralai-workflows]'
```

For the `TEMPORAL_BLOCKING` and `TEMPORAL_FIRE_AND_FORGET` execution modes, also install the `temporal` extra:

```bash
pip install 'pipelex[mistralai-workflows,temporal]'
```

The framework-agnostic core (`bridge.py`, `execution_mode.py`, `bootstrap.py`, `exceptions.py`) is importable on a venv that does NOT have `mistralai-workflows` installed. The optional-dep guard fires only when you import `pipelex.plugins.mistralai_workflows.activities` (or `streaming` once shipped).

---

## What you can import

Per Pipelex's no-re-exports rule, import from the full path:

```python
from pipelex.plugins.mistralai_workflows.activities import pipelex_run_pipe
from pipelex.plugins.mistralai_workflows.bridge import (
    PipelexPipeRunInput,
    PipelexPipeRunOutput,
    run_pipe_via_bridge,
)
from pipelex.plugins.mistralai_workflows.execution_mode import PipelexExecutionMode
from pipelex.plugins.mistralai_workflows.bootstrap import (
    ensure_pipelex_booted,
    get_pipelex_dependency,
)
```

---

## Execution modes

`PipelexExecutionMode` is set per-call via `PipelexPipeRunInput.execution_mode`. It is exhaustive: any new mode added later will surface as a linting error in every `match` statement that consumes it.

### `DIRECT`

The pipe runs in-process inside the Mistral activity. No Temporal involvement on Pipelex's side. The activity blocks until the pipe completes.

- **When to use:** simple integrations, fast feedback, tests, environments without a Pipelex Temporal worker.
- **Requires:** `pipelex[mistralai-workflows]`.

### `TEMPORAL_BLOCKING`

The bridge dispatches the pipe as a Pipelex Temporal workflow (`WfPipeRun`) and awaits completion. The pipe runs durably on the Pipelex worker fleet; the Mistral activity blocks until that workflow returns.

- **When to use:** you already operate a Pipelex Temporal cluster and want pipes to run durably with Pipelex's existing observability and retry semantics.
- **Requires:** `pipelex[mistralai-workflows,temporal]`.

### `TEMPORAL_FIRE_AND_FORGET`

The bridge dispatches the pipe as a Pipelex Temporal workflow and returns immediately with the workflow id. The activity does NOT wait. Completion is delivered out-of-band via a `DeliveryAssignment` (storage and/or webhook).

- **When to use:** long-running pipes (multi-minute LLM jobs, large extractions) where you don't want the surrounding Mistral activity to keep its slot for the full duration.
- **Requires:** `pipelex[mistralai-workflows,temporal]`.
- **Validation:** `delivery_assignment_dump` must be set; otherwise `run_pipe_via_bridge` raises `PipelexBridgeRuntimeError` to prevent silently-dropped completions.

---

## Boundary types

Everything that crosses the Mistral/Temporal boundary is JSON-only:

- `PipelexPipeRunInput.inputs` — `dict[str, Any]`
- `PipelexPipeRunInput.library_crate_dump` — `dict[str, Any] | None` (a `LibraryCrate.model_dump(mode="json")`)
- `PipelexPipeRunInput.delivery_assignment_dump` — `dict[str, Any] | None` (a `DeliveryAssignment.model_dump(mode="json")`)
- `PipelexPipeRunOutput.output_dict` — `dict[str, Any]` produced by `WorkingMemory.dump_for_temporal()`
- `PipelexPipeRunOutput.graph_spec_dump` — `dict[str, Any] | None`

No internal Pipelex types (`PipeJob`, `PipeOutput`, `WorkingMemory`) cross the activity boundary. The bridge serializes via `WorkingMemory.dump_for_temporal()` regardless of execution mode, so the `output_dict` shape is stable.

---

## Bootstrapping

Boot Pipelex once before the Mistral worker starts; the activity is then a thin wrapper around `run_pipe_via_bridge`:

```python
import asyncio
from mistralai import workflows

from pipelex.plugins.mistralai_workflows.activities import pipelex_run_pipe
from pipelex.plugins.mistralai_workflows.bootstrap import ensure_pipelex_booted


async def main() -> None:
    ensure_pipelex_booted()
    await workflows.run_worker([MyFlow], activities=[pipelex_run_pipe])


asyncio.run(main())
```

`ensure_pipelex_booted()` is idempotent and safe to call from inside the activity too — useful for tests or first-run safety nets — but in production it should be called explicitly at worker startup so Pipelex initialization is not on the critical path of the first activity.

---

## Per-call library scoping (`library_crate_dump`)

When a `library_crate_dump` is provided on the input, the bridge opens a per-call scoped library, loads the crate, runs the pipe inside that scope, and tears down on the way out. The global registry is left untouched.

This is the same scoping mechanism Pipelex's own Temporal layer uses (`pipelex/temporal/tprl_pipe/wf_pipe_router.py`) and is the recommended way to invoke a pipe whose bundle is not pre-loaded into the worker's global registry — for example, when the calling activity received the bundle as part of an API request.

---

## Error mapping

The bridge maps Pipelex execution errors into a single `PipelexBridgeRuntimeError` chained from the original exception. Mistral / Temporal infrastructure errors (connection, dispatch) propagate unchanged.

| Exception                              | When                                                                          |
| -------------------------------------- | ----------------------------------------------------------------------------- |
| `MistralWorkflowsNotInstalledError`    | Importing `activities` (or `streaming`) without the optional dep installed    |
| `MissingPipelexTemporalExtraError`     | Calling `TEMPORAL_*` modes without `pipelex[temporal]` installed              |
| `PipelexBridgeRuntimeError`            | Pipe execution failed; original exception is on `__cause__`                   |
| `MistralWorkflowsPluginError`          | Common base for plugin-specific errors                                        |

---

## Boundary semantics summary

| Aspect                  | DIRECT                | TEMPORAL_BLOCKING                | TEMPORAL_FIRE_AND_FORGET             |
| ----------------------- | --------------------- | -------------------------------- | ------------------------------------ |
| Pipelex worker required | No                    | Yes                              | Yes                                  |
| Activity blocks         | Yes                   | Yes (until WfPipeRun completes)  | No (returns workflow_id immediately) |
| `is_completed` returned | `True`                | `True`                           | `False`                              |
| `workflow_id` returned  | `None`                | Pipelex Temporal workflow id     | Pipelex Temporal workflow id         |
| `output_dict` populated | Yes                   | Yes                              | `{}`                                 |
| Completion delivery     | In-band               | In-band                          | Out-of-band via `DeliveryAssignment` |
