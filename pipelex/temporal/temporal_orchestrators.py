"""Temporal orchestrators (in-tree for Phase 3; externalized in Phase 5).

``TemporalBlockingOrchestrator`` / ``TemporalFireAndForgetOrchestrator`` are
extracted verbatim from the bridge's old ``_run_temporal_*`` arms so the bridge
dispatches by mode through the ``OrchestratorRegistry``. They are registered
unconditionally by the Temporal plugin (regardless of ``temporal.is_enabled``),
but each guards on the ``pipelex[temporal]`` extra at the top of ``run`` and
surfaces a friendly ``MissingOrchestratorError`` when it is absent.

Import-light: this module imports no ``temporalio`` at module scope — both the
extra guard (``find_spec``) and the workflow-run factory/exceptions are resolved
lazily inside ``run``. Constructing an instance therefore pulls no host-runtime
SDK, which is what keeps boot import-light when ``temporal.is_enabled`` is False.
"""

from __future__ import annotations

import importlib.util
from typing import TYPE_CHECKING

from pipelex.runtime_bridge.exceptions import MissingOrchestratorError, PipelexBridgeDispatchError
from pipelex.runtime_bridge.execution_mode import PipelexExecutionMode
from pipelex.runtime_bridge.payloads import PipelexPipeRunOutput
from pipelex.runtime_bridge.serialization import PIPE_DISPATCH_ERRORS, serialize_completed_output

if TYPE_CHECKING:
    from pipelex.base_exceptions import PipelexError
    from pipelex.pipe_run.delivery_assignment import DeliveryAssignment
    from pipelex.pipe_run.pipe_job import PipeJob


def _require_temporal_extra(*, mode: PipelexExecutionMode) -> None:
    """Fail loud with the exact install hint when the pipelex[temporal] extra is absent.

    Uses ``find_spec`` (no import) so the check itself stays import-light; a deeper
    import failure inside an installed ``temporalio`` chain is deliberately NOT
    relabelled — it propagates raw, since it is a real bug, not a missing extra.
    """
    if importlib.util.find_spec("temporalio") is None:
        raise MissingOrchestratorError(mode=mode)


class TemporalBlockingOrchestrator:
    """Dispatch the pipe as a Pipelex Temporal workflow and await its completion."""

    async def run(self, *, pipe_job: PipeJob, delivery_assignment: DeliveryAssignment | None) -> PipelexPipeRunOutput:
        _require_temporal_extra(mode=PipelexExecutionMode.TEMPORAL_BLOCKING)

        from pipelex.temporal.exceptions import WorkflowExecutionError  # noqa: PLC0415
        from pipelex.temporal.tprl_pipe.temporal_pipe_run import make_temporal_pipe_run  # noqa: PLC0415

        # A pipe failure inside the Temporal workflow surfaces as WorkflowExecutionError (a
        # TemporalFlowError, not in PIPE_DISPATCH_ERRORS); catch it too so a Temporal-mode failure is
        # wrapped just like DIRECT/mistral. `from exc` keeps its structured ErrorReport reachable.
        dispatch_errors: tuple[type[PipelexError], ...] = (*PIPE_DISPATCH_ERRORS, WorkflowExecutionError)
        temporal_pipe_run = make_temporal_pipe_run()
        try:
            pipe_output = await temporal_pipe_run.run(pipe_job=pipe_job, delivery_assignment=delivery_assignment)
        except dispatch_errors as exc:
            msg = f"Pipe execution failed in TEMPORAL_BLOCKING mode for pipe '{pipe_job.pipe.code}': {exc}"
            raise PipelexBridgeDispatchError(msg) from exc

        # Report the actual Temporal workflow id, not the bare pipeline_run_id. run() started the
        # workflow with make_workflow_id(pipeline_run_id), which prefixes the id in non-NORMAL run modes
        # (ut-/ci-/cc-/cct- — see temporal_manager.make_top_workflow_id); the bare pipeline_run_id would
        # not resolve there. Recomputing via the same make_workflow_id keeps a single source of truth and
        # matches the id fire-and-forget returns from start(). In production (RunMode.NORMAL) the prefix
        # is empty, so this equals pipeline_run_id.
        workflow_id = temporal_pipe_run.make_workflow_id(pipeline_run_id=pipe_job.job_metadata.pipeline_run_id)

        return serialize_completed_output(
            pipe_output=pipe_output,
            workflow_id=workflow_id,
        )


class TemporalFireAndForgetOrchestrator:
    """Dispatch the pipe as a Pipelex Temporal workflow and return immediately."""

    async def run(self, *, pipe_job: PipeJob, delivery_assignment: DeliveryAssignment | None) -> PipelexPipeRunOutput:
        _require_temporal_extra(mode=PipelexExecutionMode.TEMPORAL_FIRE_AND_FORGET)

        from pipelex.temporal.exceptions import WorkflowExecutionError  # noqa: PLC0415
        from pipelex.temporal.tprl_pipe.temporal_pipe_run import make_temporal_pipe_run  # noqa: PLC0415

        # start() raises WorkflowExecutionError on a dispatch failure (a TemporalFlowError, not in
        # PIPE_DISPATCH_ERRORS); catch it too so fire-and-forget dispatch failures wrap uniformly.
        dispatch_errors: tuple[type[PipelexError], ...] = (*PIPE_DISPATCH_ERRORS, WorkflowExecutionError)
        temporal_pipe_run = make_temporal_pipe_run()
        try:
            workflow_id, _handle = await temporal_pipe_run.start(pipe_job=pipe_job, delivery_assignment=delivery_assignment)
        except dispatch_errors as exc:
            msg = f"Pipe dispatch failed in TEMPORAL_FIRE_AND_FORGET mode for pipe '{pipe_job.pipe.code}': {exc}"
            raise PipelexBridgeDispatchError(msg) from exc

        return PipelexPipeRunOutput(
            output_dict={},
            main_stuff_name=None,
            pipeline_run_id=pipe_job.job_metadata.pipeline_run_id,
            workflow_id=workflow_id,
            is_completed=False,
            graph_spec_dump=None,
        )
