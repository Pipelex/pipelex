---
title: "Mistral Workflows Recipes"
description: "Three integration tiers for invoking Pipelex pipes from Mistral Workflows activities — pre-decorated, helper-in-your-own-activity, full control."
---

# Mistral Workflows Recipes

For the architecture and execution-mode reference, see the [plugin overview](./mistralai-workflows-plugin.md).

The plugin offers three usage tiers, in order of decreasing convenience and increasing control. Pick the tier that matches how much customization you need around the activity itself.

---

## Tier 1 — pre-decorated activity (the fast path)

Use the ready-made `pipelex_run_pipe` activity directly. Nothing to configure beyond pipe code and inputs.

```python
import asyncio
from mistralai import workflows

from pipelex.plugins.mistralai_workflows.activities import pipelex_run_pipe
from pipelex.plugins.mistralai_workflows.bootstrap import ensure_pipelex_booted
from pipelex.plugins.mistralai_workflows.bridge import PipelexPipeRunInput
from pipelex.plugins.mistralai_workflows.execution_mode import PipelexExecutionMode


@workflows.workflow.define(name="extract-invoice-flow")
class ExtractInvoiceFlow:
    @workflows.workflow.entrypoint
    async def run(self, doc_url: str) -> dict:
        result = await pipelex_run_pipe(
            PipelexPipeRunInput(
                pipe_code="finance.extract_invoice",
                inputs={"doc_url": doc_url},
                execution_mode=PipelexExecutionMode.DIRECT,
            )
        )
        return result.output_dict


async def main() -> None:
    ensure_pipelex_booted()
    await workflows.run_worker([ExtractInvoiceFlow], activities=[pipelex_run_pipe])


asyncio.run(main())
```

The activity has sensible defaults (10 minute timeout, 3 retries). When you need different timeouts, retry policies, rate limits, or sticky-to-worker behavior — go to Tier 2.

---

## Large payloads — `pipelex_run_pipe_offloaded`

Temporal's per-event payload limit is around 2 MiB. When a pipe input or output approaches that ceiling — large documents, accumulated transcripts, image bytes — the activity rejects with `MessageTooLarge`. Mistral Workflows ships an `ActivityInOutOffloadingInterceptor` that streams oversized payloads through blob storage (S3/GCS/Azure) automatically, and Pipelex provides an offload-capable activity to plug into it.

```python
from mistralai import workflows
from mistralai.workflows.core.encoding.fields_offloader import OffloadableField

from pipelex.plugins.mistralai_workflows.activities import (
    PipelexPipeRunInputOffloaded,
    PipelexPipeRunOutputOffloaded,
    pipelex_run_pipe_offloaded,
)
from pipelex.plugins.mistralai_workflows.bridge import PipelexPipeRunInput


@workflows.workflow.define(name="extract-large-doc-flow")
class ExtractLargeDocFlow:
    @workflows.workflow.entrypoint
    async def run(self, doc_bytes: bytes) -> dict:
        wrapped_input = PipelexPipeRunInputOffloaded(
            payload=OffloadableField(
                value=PipelexPipeRunInput(
                    pipe_code="finance.extract_large_invoice",
                    inputs={"doc_bytes": doc_bytes.hex()},
                ),
            ),
        )
        wrapped_output: PipelexPipeRunOutputOffloaded = await pipelex_run_pipe_offloaded(wrapped_input)
        return wrapped_output.payload.get_value().output_dict
```

The wrapping/unwrapping is a no-op when the payload fits inline. Offloading only kicks in when the worker is configured with the interceptor:

```python
from mistralai import workflows
from mistralai.workflows.core.config.config import config
from mistralai.workflows.core.encoding.fields_offloader import FieldsOffloader
from mistralai.workflows.core.temporal.activity_offloading_interceptor import (
    ActivityInOutOffloadingInterceptor,
)

offloader = FieldsOffloader(offloading_config=config.payload_offloading)
interceptor = ActivityInOutOffloadingInterceptor(offloader)

await workflows.run_worker(
    [ExtractLargeDocFlow],
    activities=[pipelex_run_pipe_offloaded],
    interceptors=[interceptor],
)
```

Trade-off: offloaded payloads live in the blob storage you configure (S3 by default in Mistral's example) for the lifetime of the workflow run. They incur storage cost and add an extra round-trip per offloaded field. Reach for the offloaded variant only when you actually need the size headroom.

---

## Live progress events — `pipelex_run_pipe_streaming`

When a UI subscribes to a Mistral Workflow execution and needs to "see something happen" while a Pipelex pipe runs, use the streaming variant. It wraps the same bridge call in a single Mistral `Task` whose lifecycle (`CustomTaskStarted` → `CustomTaskInProgress` → `CustomTaskCompleted` / `CustomTaskFailed`) is published to whatever events client your worker is configured with.

```python
from mistralai import workflows

from pipelex.plugins.mistralai_workflows.bridge import (
    PipelexPipeRunInput,
    PipelexPipeRunOutput,
)
from pipelex.plugins.mistralai_workflows.execution_mode import PipelexExecutionMode
from pipelex.plugins.mistralai_workflows.streaming import pipelex_run_pipe_streaming


@workflows.workflow.define(name="extract-invoice-streaming-flow")
class ExtractInvoiceStreamingFlow:
    @workflows.workflow.entrypoint
    async def run(self, doc_url: str) -> dict:
        result: PipelexPipeRunOutput = await pipelex_run_pipe_streaming(
            PipelexPipeRunInput(
                pipe_code="finance.extract_invoice",
                inputs={"doc_url": doc_url},
                execution_mode=PipelexExecutionMode.DIRECT,
            )
        )
        return result.output_dict


await workflows.run_worker(
    [ExtractInvoiceStreamingFlow],
    activities=[pipelex_run_pipe_streaming],
)
```

The events carry a small JSON payload identifying the run:

| Event                    | Payload                                                                       |
| ------------------------ | ----------------------------------------------------------------------------- |
| `CustomTaskStarted`      | `phase="started"`, `pipe_code`, `execution_mode`, `pipeline_run_id` (if set)  |
| `CustomTaskInProgress`   | JSON-patch updates: per-step boundaries (DIRECT mode) and the final transition to `phase="completed"` |
| `CustomTaskCompleted`    | Final full-state snapshot with `phase="completed"` and `main_stuff_name`      |
| `CustomTaskFailed`       | The original exception message (emitted by `Task.__aexit__` on failure)       |

`custom_task_type` is always `"pipelex.pipe_run"`, so subscribers can filter on it without parsing the payload.

### Per-step events for `DIRECT` mode

When `execution_mode=PipelexExecutionMode.DIRECT`, the streaming activity publishes one `CustomTaskInProgress` event per Pipelex pipe boundary in addition to the final completed-state push. Each pipe-step event carries a JSON-patch update to the streaming state with the following fields:

| Field                       | Description                                                                  |
| --------------------------- | ---------------------------------------------------------------------------- |
| `phase`                     | `"in_progress"` (transition from `"started"` on the very first patch)        |
| `current_step_pipe_code`    | The pipe code for the most recent `PipeStartEvent`                           |
| `current_step_node_id`      | The graph node id for that pipe                                              |
| `last_event_kind`           | `"pipe_start"` / `"pipe_end_success"` / `"pipe_end_error"`                   |
| `started_steps`             | Cumulative count of pipe-step starts (1-indexed, monotonic)                  |
| `completed_steps`           | Cumulative count of successful pipe-step completions                         |
| `last_output_stuff_name`    | The output IOSpec name for the most recent successful step (or `null`)       |

A field only appears in a given `CustomTaskInProgress` JSON-patch when its value actually changed — for example, `last_event_kind` won't appear in two consecutive `pipe_start` events. Use `started_steps` / `completed_steps` (always changing) as discriminators when you need to count or order step events.

`TEMPORAL_BLOCKING` and `TEMPORAL_FIRE_AND_FORGET` modes keep the simpler "one started + one completed" semantics — per-step streaming across the Temporal worker boundary is not supported in this release.

For the silent path (no observability, no event publishing overhead per activity) keep using `pipelex_run_pipe` — the streaming variant is opt-in.

---

## Tier 2 — helper inside your own typed activity

Wrap `run_pipe_via_bridge` in your own `@activity`-decorated function so you control all activity options and the input/output types.

```python
from datetime import timedelta

from mistralai import workflows
from pydantic import BaseModel

from pipelex.plugins.mistralai_workflows.bridge import (
    PipelexPipeRunInput,
    run_pipe_via_bridge,
)


class InvoiceData(BaseModel):
    invoice_number: str
    total_amount: float
    currency: str


@workflows.activity(
    start_to_close_timeout=timedelta(minutes=30),
    retry_policy_max_attempts=5,
)
async def extract_invoice(doc_url: str) -> InvoiceData:
    out = await run_pipe_via_bridge(
        PipelexPipeRunInput(
            pipe_code="finance.extract_invoice",
            inputs={"doc_url": doc_url},
        )
    )
    main_stuff = out.output_dict["root"][out.main_stuff_name]
    return InvoiceData.model_validate(main_stuff["content"])
```

The `run_pipe_via_bridge` helper is the same code the Tier 1 activity calls — just without the decoration. This is the recommended tier for production: you keep typed activity inputs/outputs, custom retries per pipe, and you can register multiple pipe-specific activities (`extract_invoice`, `summarize_contract`, ...) on the same Mistral worker.

---

## Tier 3 — full control (`library_crate_dump`)

Tier 3 is for cases where the Pipelex bundle is not pre-loaded into the worker's global registry — for example, the calling Mistral workflow received the bundle as part of an API request and needs to run a pipe defined in it without polluting the shared library.

```python
from mistralai import workflows

from pipelex.plugins.mistralai_workflows.bridge import (
    PipelexPipeRunInput,
    run_pipe_via_bridge,
)


@workflows.activity()
async def run_user_supplied_pipe(
    pipe_code: str,
    inputs: dict,
    library_crate_dump: dict,
) -> dict:
    out = await run_pipe_via_bridge(
        PipelexPipeRunInput(
            pipe_code=pipe_code,
            inputs=inputs,
            library_crate_dump=library_crate_dump,
        )
    )
    return out.output_dict
```

The bridge opens a per-call scoped library, loads the crate, runs the pipe, and tears the scope down on the way out. The global registry is untouched — concurrent activities with different `library_crate_dump`s do not see each other's classes.

To produce the dump on the submitter side:

```python
from pipelex.hub import get_library_manager

crate = get_library_manager().get_crate(library_id=my_lib_id)
crate_dump = crate.model_dump(mode="json")
```

---

## Picking an execution mode

| You want…                                                            | Use                          |
| -------------------------------------------------------------------- | ---------------------------- |
| Run a pipe in-process inside the Mistral activity                    | `DIRECT`                     |
| Hand off pipe execution to your existing Pipelex Temporal cluster    | `TEMPORAL_BLOCKING`          |
| Don't block the activity for a long-running pipe; deliver out-of-band | `TEMPORAL_FIRE_AND_FORGET`   |

`TEMPORAL_FIRE_AND_FORGET` requires `delivery_assignment_dump` so the completion can reach somebody — webhook, storage target, or both.

```python
from pipelex.pipe_run.delivery_assignment import (
    DeliveryAssignment,
    StorageTarget,
    WebhookTarget,
)

delivery = DeliveryAssignment(
    storage=StorageTarget(key_prefix="invoices/2026/"),
    webhooks=[WebhookTarget(url="https://my.app/pipelex-callback")],
)

result = await run_pipe_via_bridge(
    PipelexPipeRunInput(
        pipe_code="finance.extract_invoice",
        inputs={"doc_url": doc_url},
        execution_mode=PipelexExecutionMode.TEMPORAL_FIRE_AND_FORGET,
        delivery_assignment_dump=delivery.model_dump(mode="json"),
    )
)
# result.is_completed is False
# result.workflow_id is the Pipelex Temporal workflow id
# Completion arrives at the webhook + storage location later.
```
