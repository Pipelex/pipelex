"""Library-lifecycle guarantee for :meth:`PipelexMTHDSProtocol.execute`.

Pins that a *successful* run RESTORES the caller's outer current-library instead of
clobbering it to ``None``.

``pipeline_run_setup`` leaves the run library open and current on success (teardown is
the caller's job — pinned by ``test_pipeline_run_setup_characterization.py``).
``execute``'s ``finally`` then tears the run library down, and must restore the
outer binding the caller held before the run — mirroring ``pipeline_run_setup``'s own
error-path restore. Without that, a run started inside an outer-library context leaves the
next operation with "No current library set" (or silently falling back to the global class
registry).

These cases run fully dry (``PipeRunMode.DRY`` + ``mock_inputs``) so no inference happens.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from typing_extensions import override

from pipelex.config import get_config
from pipelex.hub import (
    clear_current_library,
    get_current_library_id_or_none,
    get_library_manager,
    set_current_library,
)
from pipelex.pipe_run.exceptions import PipeRouterError
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipe_run.pipe_run_protocol import PipeRunProtocol
from pipelex.pipeline.exceptions import PipelineExecutionError
from pipelex.pipeline.runner import PipelexMTHDSProtocol

if TYPE_CHECKING:
    from collections.abc import Callable

    from pipelex.core.pipes.pipe_output import PipeOutput
    from pipelex.pipe_run.delivery_assignment import DeliveryAssignment
    from pipelex.pipe_run.pipe_job import PipeJob
    from pipelex.system.configuration.configs import PipelineExecutionConfig

_RUNNER_LIFECYCLE_DOMAIN = "runner_lifecycle"
_RUNNER_LIFECYCLE_MTHDS = f"""
domain = "{_RUNNER_LIFECYCLE_DOMAIN}"
description = "Minimal bundle for runner library-lifecycle tests"

[concept.Topic]
description = "A topic"

[concept.Topic.structure]
name = {{ type = "text", description = "Topic name" }}

[pipe.echo_topic]
type = "PipeLLM"
description = "Pipe used only to exercise the runner library lifecycle"
inputs = {{ subject = "Text" }}
output = "Topic"
prompt = "Echo the $subject as a topic"
"""


def _dry_mock_config() -> PipelineExecutionConfig:
    return get_config().pipelex.pipeline_execution_config.with_execution_overrides(
        generate_graph=False,
        mock_inputs=True,
    )


class _FailingPipeRun(PipeRunProtocol):
    """A PipeRun whose ``run`` always raises, so the failure lands in ``execute``'s finally
    AFTER setup has succeeded and resolved the run library — exercising the runner's own teardown guard.
    """

    @override
    async def run(self, pipe_job: PipeJob, *, delivery_assignment: DeliveryAssignment | None = None) -> PipeOutput:
        msg = "Injected pipe-run failure to exercise library teardown."
        raise PipeRouterError(
            message=msg,
            run_mode=PipeRunMode.DRY,
            pipe_code=pipe_job.pipe.code,
            output_name=pipe_job.output_name,
            pipe_stack=[],
        )


@pytest.mark.asyncio(loop_scope="class")
class TestRunnerLibraryLifecycle:
    async def test_success_restores_outer_current_library(self, load_empty_library: Callable[[], str]) -> None:
        # A run started inside an outer-library context must leave that outer library current after a
        # SUCCESSFUL run. We pass no library_id, so the run uses its own auto-generated library id;
        # execute's finally tears that run library down and must RESTORE the outer binding
        # rather than clear it to None.
        outer_library_id = load_empty_library()
        try:
            runner = PipelexMTHDSProtocol(
                pipe_run_mode=PipeRunMode.DRY,
                execution_config=_dry_mock_config(),
            )
            await runner.execute(
                pipe_code="echo_topic",
                mthds_contents=[_RUNNER_LIFECYCLE_MTHDS],
            )
            # Restored to the outer id, not clobbered to None.
            assert get_current_library_id_or_none() == outer_library_id
        finally:
            clear_current_library()

    async def test_success_clears_when_no_outer_library(self) -> None:
        # With no outer current-library, a successful run leaves no current library — the no-outer
        # branch still clears (set_current_library cannot take None). Clearing first makes this
        # deterministic under xdist's per-worker shared current-library state.
        clear_current_library()
        runner = PipelexMTHDSProtocol(
            pipe_run_mode=PipeRunMode.DRY,
            execution_config=_dry_mock_config(),
        )
        await runner.execute(
            pipe_code="echo_topic",
            mthds_contents=[_RUNNER_LIFECYCLE_MTHDS],
        )
        assert get_current_library_id_or_none() is None

    async def test_failure_when_outer_is_run_library_clears_instead_of_dangling(self) -> None:
        # execute's OWN finally guard, mirroring pipeline_run_setup's edge: when the runner's
        # library_id equals the outer current-library, prev == library_id_resolved. Restoring then
        # tearing down the same id would leave current-library pointing at a torn-down library; the guard
        # clears instead. Setup succeeds (echo_topic resolves), then the injected pipe_run raises so the
        # failure lands in the finally with library_id_resolved set to the colliding id.
        library_manager = get_library_manager()
        collide_library_id, _ = library_manager.open_library()
        set_current_library(library_id=collide_library_id)
        try:
            runner = PipelexMTHDSProtocol(
                library_id=collide_library_id,
                pipe_run_mode=PipeRunMode.DRY,
                execution_config=_dry_mock_config(),
                pipe_run=_FailingPipeRun(),
            )
            with pytest.raises(PipelineExecutionError):
                await runner.execute(
                    pipe_code="echo_topic",
                    mthds_contents=[_RUNNER_LIFECYCLE_MTHDS],
                )
            # Cleared, not left dangling at the just-torn-down collide id.
            assert get_current_library_id_or_none() is None
        finally:
            clear_current_library()
