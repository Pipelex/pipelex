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
