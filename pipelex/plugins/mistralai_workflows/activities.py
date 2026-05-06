"""Tier 1 — pre-decorated Mistral Workflows activity that runs a Pipelex pipe.

Importing this module triggers the optional-dep guard: if
``mistralai-workflows`` is not installed, the import fails fast with a
``MistralWorkflowsNotInstalledError`` carrying install instructions.

Two activity variants are exposed:

- ``pipelex_run_pipe`` — inline boundary types. Use when payloads stay below
  Temporal's per-event size limit (~2 MiB).
- ``pipelex_run_pipe_offloaded`` — boundary types wrapped in
  ``OffloadableField`` so Mistral's ``ActivityInOutOffloadingInterceptor``
  can stream the payload through blob storage when it exceeds the configured
  threshold. Requires the user to register the interceptor on their worker
  (see Mistral's ``workflow_activity_offloading`` example).
"""

from datetime import timedelta

from pipelex.plugins.mistralai_workflows.bridge import (
    PipelexPipeRunInput,
    PipelexPipeRunOutput,
    run_pipe_via_bridge,
)
from pipelex.plugins.mistralai_workflows.exceptions import MistralWorkflowsNotInstalledError

try:
    from mistralai.workflows import activity
    from mistralai.workflows.core.encoding.fields_offloader import OffloadableField, OffloadableModel
except ImportError as exc:
    msg = (
        "The 'mistralai-workflows' optional dependency is required to use "
        "pipelex.plugins.mistralai_workflows.activities. "
        "Install with: pip install 'pipelex[mistralai-workflows]'"
    )
    raise MistralWorkflowsNotInstalledError(msg) from exc


class PipelexPipeRunInputOffloaded(OffloadableModel):
    """Offload-capable variant of ``PipelexPipeRunInput``.

    Wraps the inline ``PipelexPipeRunInput`` in an ``OffloadableField`` so the
    ``ActivityInOutOffloadingInterceptor`` can stream the payload to blob
    storage when its serialized size exceeds the configured threshold.
    """

    payload: OffloadableField[PipelexPipeRunInput]


class PipelexPipeRunOutputOffloaded(OffloadableModel):
    """Offload-capable variant of ``PipelexPipeRunOutput``.

    Mirrors ``PipelexPipeRunInputOffloaded`` for the return path.
    """

    payload: OffloadableField[PipelexPipeRunOutput]


@activity(
    start_to_close_timeout=timedelta(minutes=10),
    retry_policy_max_attempts=3,
)
async def pipelex_run_pipe(input_payload: PipelexPipeRunInput) -> PipelexPipeRunOutput:
    """Run a Pipelex pipe from inside a Mistral Workflows activity.

    Thin wrapper around ``run_pipe_via_bridge`` so users get a ready-to-register
    activity without having to write their own ``@activity`` decoration. For
    custom timeouts, retry policies, rate limits, or sticky-to-worker config,
    call ``run_pipe_via_bridge`` directly from your own ``@activity`` (Tier 2).
    """
    return await run_pipe_via_bridge(input_payload)


@activity(
    start_to_close_timeout=timedelta(minutes=10),
    retry_policy_max_attempts=3,
)
async def pipelex_run_pipe_offloaded(
    input_payload: PipelexPipeRunInputOffloaded,
) -> PipelexPipeRunOutputOffloaded:
    """Run a Pipelex pipe with offload-capable boundary types.

    Same semantics as ``pipelex_run_pipe`` but the input/output are wrapped
    in ``OffloadableField``. To actually offload payloads to blob storage,
    the worker must be configured with ``ActivityInOutOffloadingInterceptor``
    pointing at S3/GCS/Azure (see Mistral's
    ``workflow_activity_offloading`` example). Without that interceptor, the
    payload still rides inline through Temporal and offloading is a no-op.
    """
    pipe_input = input_payload.payload.get_value()
    pipe_output = await run_pipe_via_bridge(pipe_input)
    return PipelexPipeRunOutputOffloaded(
        payload=OffloadableField(value=pipe_output),
    )
