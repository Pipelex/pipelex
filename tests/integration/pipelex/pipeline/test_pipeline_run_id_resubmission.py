"""Per-run ``PipelineManager`` entry lifecycle across a full run — serial resubmission support.

Pins that the registry entry created by ``pipeline_run_setup`` is freed on every exit path,
so a later run can resubmit the same explicit ``pipeline_run_id`` (the hosted runner threads a
client-supplied id into ``pipeline_run_setup``; before this fix the entry was process-permanent
and every resubmission raised ``PipelineManagerAlreadyExistsError``):

- ``execute`` success: the runner's ``finally`` removes the entry.
- ``execute`` failure (pipe-run raises after setup succeeded): same ``finally`` removes it.
- ``pipeline_run_setup`` failure after registration (pipe missing from the bundle): setup removes
  its OWN registration — the runner never learns the id on this path, so setup must self-clean —
  and a resubmission of the same explicit id then succeeds.

Only genuinely concurrent same-id runs still collide in ``add_new_pipeline`` — that raise is
load-bearing (it shields the live direct-mode tracer from ``open_tracer``'s pop-and-replace
healing) and is pinned by ``tests/unit/pipelex/pipeline/test_pipeline_manager.py``.

These cases run fully dry (``PipeRunMode.DRY`` + ``mock_inputs``) so no inference happens.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from typing_extensions import override

from pipelex.config import get_config
from pipelex.graph.graph_tracer import GraphTracer
from pipelex.interpreter_hub import clear_current_library, get_current_library_id_or_none, get_library_manager, get_pipeline_manager
from pipelex.libraries.pipe.exceptions import PipeNotFoundError
from pipelex.pipe_run.exceptions import PipeRouterError
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipe_run.pipe_run_protocol import PipeRunProtocol
from pipelex.pipeline.exceptions import PipelineExecutionError
from pipelex.pipeline.pipeline_factory import PipelineFactory
from pipelex.pipeline.pipeline_run_setup import pipeline_run_setup
from pipelex.pipeline.runner import PipelexMTHDSProtocol

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

    from pipelex.core.pipes.pipe_output import PipeOutput
    from pipelex.pipe_run.delivery_assignment import DeliveryAssignment
    from pipelex.pipe_run.pipe_job import PipeJob
    from pipelex.system.configuration.configs import PipelineExecutionConfig

_RESUBMISSION_DOMAIN = "run_id_resubmission"
_RESUBMISSION_MTHDS = f"""
domain = "{_RESUBMISSION_DOMAIN}"
description = "Minimal bundle for pipeline_run_id resubmission tests"

[concept.Topic]
description = "A topic"

[concept.Topic.structure]
name = {{ type = "text", description = "Topic name" }}

[pipe.echo_topic]
type = "PipeLLM"
description = "Pipe used only to exercise the per-run registry lifecycle"
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
    """A PipeRun whose ``run`` always raises, so the failure lands in ``execute``'s
    finally AFTER setup has succeeded and registered the run — exercising the runner-side removal.
    """

    @override
    async def run(self, pipe_job: PipeJob, *, delivery_assignment: DeliveryAssignment | None = None) -> PipeOutput:
        msg = "Injected pipe-run failure to exercise registry-entry removal."
        raise PipeRouterError(
            message=msg,
            run_mode=PipeRunMode.DRY,
            pipe_code=pipe_job.pipe.code,
            output_name=pipe_job.output_name,
            pipe_stack=[],
        )


@pytest.mark.asyncio(loop_scope="class")
class TestPipelineRunIdResubmission:
    async def test_success_clears_registry_entry(self) -> None:
        runner = PipelexMTHDSProtocol(
            pipe_run_mode=PipeRunMode.DRY,
            execution_config=_dry_mock_config(),
        )
        response = await runner.execute(
            pipe_code="echo_topic",
            mthds_contents=[_RESUBMISSION_MTHDS],
        )
        assert get_pipeline_manager().get_optional_pipeline(pipeline_run_id=response.pipeline_run_id) is None

    async def test_failure_clears_registry_entry(self, mocker: MockerFixture) -> None:
        # Spy on the factory to capture the run id minted during the failing run — the
        # PipelineExecutionError doesn't carry it (the manager is a pydantic RootModel, which
        # rejects spy attribute injection).
        manager = get_pipeline_manager()
        mint_spy = mocker.spy(PipelineFactory, "make_pipeline")
        runner = PipelexMTHDSProtocol(
            pipe_run_mode=PipeRunMode.DRY,
            execution_config=_dry_mock_config(),
            pipe_run=_FailingPipeRun(),
        )
        with pytest.raises(PipelineExecutionError):
            await runner.execute(
                pipe_code="echo_topic",
                mthds_contents=[_RESUBMISSION_MTHDS],
            )
        minted_run_id = mint_spy.spy_return.pipeline_run_id
        # The runner's finally removed the failing run's entry — same id can resubmit.
        assert manager.get_optional_pipeline(pipeline_run_id=minted_run_id) is None

    async def test_setup_failure_self_cleans_and_same_id_resubmits(self) -> None:
        explicit_run_id = "resubmission-test-run-id"
        # First submission fails AFTER registration: the pipe is absent from the bundle, so
        # get_required_pipe raises inside pipeline_run_setup's try — the runner never learns the
        # id on this path, so setup must remove its own registration.
        with pytest.raises(PipeNotFoundError):
            await pipeline_run_setup(
                execution_config=_dry_mock_config(),
                mthds_contents=[_RESUBMISSION_MTHDS],
                pipe_code="absent_pipe",
                pipe_run_mode=PipeRunMode.DRY,
                pipeline_run_id=explicit_run_id,
            )
        assert get_pipeline_manager().get_optional_pipeline(pipeline_run_id=explicit_run_id) is None

        # Resubmission of the SAME explicit id now succeeds (before the fix: process-permanent
        # PipelineManagerAlreadyExistsError).
        pipe_job, pipeline_run_id, library_id = await pipeline_run_setup(
            execution_config=_dry_mock_config(),
            mthds_contents=[_RESUBMISSION_MTHDS],
            pipe_code="echo_topic",
            pipe_run_mode=PipeRunMode.DRY,
            pipeline_run_id=explicit_run_id,
        )
        try:
            assert pipeline_run_id == explicit_run_id
            assert pipe_job.pipe.code == "echo_topic"
            assert get_pipeline_manager().get_optional_pipeline(pipeline_run_id=explicit_run_id) is not None
        finally:
            # Caller-side teardown (pipeline_run_setup leaves the library open and the run
            # registered on success — execute's finally owns this in production).
            get_pipeline_manager().remove_pipeline(pipeline_run_id=explicit_run_id)
            get_library_manager().teardown(library_id=library_id)
            clear_current_library()

    async def test_setup_failure_frees_entry_even_when_tracer_teardown_raises(self, mocker: MockerFixture) -> None:
        """A raise inside the error-path tracer teardown must not strand the registry entry nor mask the original failure.

        ``close_tracer`` runs before ``remove_pipeline`` in setup's failure cleanup (that ordering
        is load-bearing — see the module docstring), and ``GraphTracer.teardown`` can raise: it
        closes the event log, and a file-backed transport's ``close()`` flushes to disk. If that
        raise skipped ``remove_pipeline`` and the library restore, the entry would be
        process-permanent again — exactly the bug this module exists to pin. And it must not
        replace the original setup failure as the propagating exception either: callers type-match
        (the runner wraps ``PipelexError`` into ``PipelineExecutionError``, the API maps error
        types to status codes), so the flush error is logged and suppressed, mirroring
        ``PipeRun.run``'s close_tracer handling.
        """
        explicit_run_id = "resubmission-teardown-raise-run-id"
        graph_config = get_config().pipelex.pipeline_execution_config.with_execution_overrides(
            generate_graph=True,
            mock_inputs=True,
        )
        outer_library_id = get_current_library_id_or_none()

        # Fail setup AFTER open_tracer so the cleanup path actually closes a tracer.
        prepare_failure_msg = "Injected post-tracer setup failure"
        prepare_mock = mocker.patch(
            "pipelex.pipeline.pipeline_run_setup.prepare_pipe_job",
            side_effect=RuntimeError(prepare_failure_msg),
        )
        # Simulate the event-log flush failing on close (e.g. NDJSON file handle on a full disk).
        teardown_mock = mocker.patch.object(
            GraphTracer,
            "teardown",
            side_effect=OSError("Injected event-log flush failure on close"),
        )

        # The ORIGINAL setup failure propagates — the flush error must not replace it.
        with pytest.raises(RuntimeError, match=prepare_failure_msg):
            await pipeline_run_setup(
                execution_config=graph_config,
                mthds_contents=[_RESUBMISSION_MTHDS],
                pipe_code="echo_topic",
                pipe_run_mode=PipeRunMode.DRY,
                pipeline_run_id=explicit_run_id,
            )

        # The suppression path was actually exercised (the cleanup did close a tracer and the
        # injected flush failure did fire) — otherwise the RuntimeError assert above is vacuous.
        teardown_mock.assert_called_once()
        # The teardown raise must not strand the entry nor clobber the caller's current-library.
        assert get_pipeline_manager().get_optional_pipeline(pipeline_run_id=explicit_run_id) is None
        assert get_current_library_id_or_none() == outer_library_id

        # Resubmission of the SAME explicit id succeeds once the fault is gone.
        mocker.stop(prepare_mock)
        mocker.stop(teardown_mock)
        pipe_job, pipeline_run_id, library_id = await pipeline_run_setup(
            execution_config=_dry_mock_config(),
            mthds_contents=[_RESUBMISSION_MTHDS],
            pipe_code="echo_topic",
            pipe_run_mode=PipeRunMode.DRY,
            pipeline_run_id=explicit_run_id,
        )
        try:
            assert pipeline_run_id == explicit_run_id
            assert pipe_job.pipe.code == "echo_topic"
        finally:
            get_pipeline_manager().remove_pipeline(pipeline_run_id=explicit_run_id)
            get_library_manager().teardown(library_id=library_id)
            clear_current_library()
