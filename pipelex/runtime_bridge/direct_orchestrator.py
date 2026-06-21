"""The core, always-on DIRECT orchestrator.

Runs a pipe in-process. Extracted verbatim from the bridge's old ``_run_direct``
arm so the bridge dispatches by mode through the ``OrchestratorRegistry`` instead
of a ``match``. Registered unconditionally by the core ``direct`` plugin.

Import-light: core pipe-run + the shared serialization helpers; no host-runtime SDK.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pipelex.hub import scoped_pipe_router
from pipelex.pipe_run.pipe_router import PipeRouter
from pipelex.pipe_run.pipe_run import PipeRun
from pipelex.runtime_bridge.exceptions import PipelexBridgeDispatchError
from pipelex.runtime_bridge.serialization import PIPE_DISPATCH_ERRORS, serialize_completed_output

if TYPE_CHECKING:
    from pipelex.pipe_run.delivery_assignment import DeliveryAssignment
    from pipelex.pipe_run.pipe_job import PipeJob
    from pipelex.runtime_bridge.payloads import PipelexPipeRunOutput


class DirectOrchestrator:
    """In-process execution; no Temporal involved on Pipelex's side."""

    async def run(self, *, pipe_job: PipeJob, delivery_assignment: DeliveryAssignment | None) -> PipelexPipeRunOutput:
        # DIRECT mode forces in-process execution even inside a Temporal-enabled
        # worker. Scope the in-process router as the active router for the WHOLE
        # run so nested controller sub-pipes — which dispatch through
        # get_pipe_router() — resolve THIS router rather than falling back to the
        # hub default. Without the scope, the hub default in a Temporal-enabled
        # worker is the Temporal router, so a DIRECT-mode sequence/batch would leak
        # its nested pipes to Temporal, defeating the point of DIRECT.
        direct_router = PipeRouter()
        with scoped_pipe_router(direct_router):
            pipe_run = PipeRun(pipe_router=direct_router)
            try:
                pipe_output = await pipe_run.run(pipe_job=pipe_job, delivery_assignment=delivery_assignment)
            except PIPE_DISPATCH_ERRORS as exc:
                msg = f"Pipe execution failed in DIRECT mode for pipe '{pipe_job.pipe.code}': {exc}"
                raise PipelexBridgeDispatchError(msg) from exc

        return serialize_completed_output(
            pipe_output=pipe_output,
            workflow_id=None,
        )
