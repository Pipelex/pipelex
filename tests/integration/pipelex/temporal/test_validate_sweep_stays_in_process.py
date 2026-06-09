"""Mode-1 Temporal guard: the BundleValidator dry-run sweep must NOT dispatch to Temporal.

Deployment-faithful companion to the in-process sentinel regression test in
``tests/integration/pipelex/pipeline/test_bundle_validator.py``
(``test_standalone_batch_sweep_scopes_in_process_router``). Where the sentinel installs a *raising
stand-in* as the hub default, this test resolves the **real** ``TemporalPipeRouter`` as the hub
default — wired by this suite's ``boot_temporal`` fixture exactly as a Temporal-enabled API process
wires it in ``pipelex.pipelex``. It therefore proves the config -> hub-default *wiring* the sentinel
deliberately bypasses, on top of the same contract.

The bug it guards: a standalone ``PipeBatch`` swept directly fans out over a mock list and
dispatches each branch through ``get_pipe_router()``. Without the sweep scoping its own in-process
router, those branches resolve the hub default — the ``TemporalPipeRouter`` — and fire concurrent
top-level workflow dispatches (``WorkflowExecutor.execute_workflow``), which produced the production
HTTP 422.

The contract asserted: the whole sweep stays in-process, so the submitter-side top-level dispatch
seam (``WorkflowExecutor.execute_workflow``) is never reached. Spying on that seam is the
deterministic analogue of the Mode-2 "worker received no dispatch" check. No live Temporal server is
needed precisely because GREEN means no dispatch ever happens; if the fix regressed, the spy fires
and the test goes RED.
"""

from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from pipelex.hub import clear_current_library, get_library_manager, get_pipelex_hub, get_required_pipe
from pipelex.pipeline.bundle_validator import BundleValidator
from pipelex.pipeline.execution_seams import acquire_library
from pipelex.temporal.tprl.workflow_caller import WorkflowExecutor
from pipelex.temporal.tprl_pipe.temporal_pipe_router import TemporalPipeRouter
from tests.integration.pipelex.temporal.test_data import PipeBatchTemporalTestData

# The standalone ``type = "PipeBatch"`` pipe in temporal_batch.mthds — swept directly it fans out,
# which is the exact shape that turned the leak fatal (concurrent same-id top-level dispatches).
_STANDALONE_BATCH_PIPE_REF = f"{PipeBatchTemporalTestData.DOMAIN}.batch_temporal_describe_topics"


@pytest.mark.temporal
@pytest.mark.asyncio(loop_scope="class")
class TestValidateSweepStaysInProcess:
    async def test_standalone_batch_sweep_never_dispatches_to_temporal(self, mocker: MockerFixture) -> None:
        # Precondition (the wiring this test exists to prove): under boot_temporal the hub default
        # router IS the real TemporalPipeRouter — the same router a Temporal-enabled API process runs.
        hub = get_pipelex_hub()
        assert isinstance(hub.get_required_pipe_router(), TemporalPipeRouter), (
            "Temporal suite precondition: the hub default router must be the real TemporalPipeRouter"
        )

        # Spy on the submitter-side top-level dispatch seam. A standalone-batch sweep that leaked to
        # Temporal would reach this exact method (TemporalPipeRouter._run_pipe_job top-level branch ->
        # WorkflowExecutorFactory.create_executor(...).execute_workflow(...)). With the fix the sweep
        # stays in-process and never touches it.
        execute_workflow_spy = mocker.spy(WorkflowExecutor, "execute_workflow")

        library_manager = get_library_manager()
        library_id = "validate_sweep_temporal_leak_lib"
        mthds_content = Path(PipeBatchTemporalTestData.BUNDLE_FILE).read_text(encoding="utf-8")
        acquire_library(library_id=library_id, mthds_contents=[mthds_content])
        try:
            batch_pipe = get_required_pipe(pipe_code=_STANDALONE_BATCH_PIPE_REF)
            results = await BundleValidator().validate_pipes([batch_pipe], library_id=library_id)
            assert results[_STANDALONE_BATCH_PIPE_REF].status.is_success
            execute_workflow_spy.assert_not_called()
        finally:
            library_manager.teardown(library_id=library_id)
            clear_current_library()
