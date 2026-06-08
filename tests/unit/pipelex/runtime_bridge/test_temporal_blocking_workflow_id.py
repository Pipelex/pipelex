"""TEMPORAL_BLOCKING reports the actual Temporal workflow id, not the bare run id.

``TemporalPipeRun.run()`` starts the workflow with ``make_workflow_id(pipeline_run_id)``,
which prefixes the id in non-NORMAL run modes (``ut-``/``ci-``/``cc-``/``cct-`` — pinned
per run mode by ``tests/unit/pipelex/temporal/test_workflow_id_construction.py``). The bridge
must surface that same id so a caller can query/cancel the real workflow — matching what
fire-and-forget already returns from ``start()``. This test pins the *wiring* (the bridge
reports ``make_workflow_id``'s output, called with the job's pipeline_run_id), independent of
the prefix table; the prefixing itself is covered by the temporal-manager test above.
"""

import pytest
from pytest_mock import MockerFixture

from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.pipe_run.pipe_job import PipeJob
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.pipeline.job_metadata import JobMetadata
from pipelex.runtime_bridge.bridge import PipelexPipeRunInput, run_pipe_via_bridge
from pipelex.runtime_bridge.execution_mode import PipelexExecutionMode


def _fake_pipe_job(mocker: MockerFixture) -> PipeJob:
    fake_pipe = mocker.MagicMock()
    fake_pipe.code = "fake_pipe"
    fake_pipe.domain_code = "fake_domain"
    return PipeJob.model_construct(
        pipe=fake_pipe,
        working_memory=WorkingMemoryFactory.make_empty(),
        pipe_run_params=PipeRunParamsFactory.make_run_params(),
        job_metadata=JobMetadata(user_id="anonymous", pipeline_run_id="bare-run-id"),
        library_crate=None,
    )


@pytest.mark.asyncio
class TestTemporalBlockingWorkflowId:
    async def test_blocking_reports_make_workflow_id_not_bare_run_id(self, mocker: MockerFixture) -> None:
        fake_job = _fake_pipe_job(mocker)
        mocker.patch("pipelex.runtime_bridge.bridge.build_pipe_job_from_input", return_value=fake_job)

        fake_factory = mocker.patch("pipelex.temporal.tprl_pipe.temporal_pipe_run.make_temporal_pipe_run")
        temporal_pipe_run = fake_factory.return_value
        temporal_pipe_run.run = mocker.AsyncMock(
            return_value=PipeOutput(working_memory=WorkingMemoryFactory.make_empty(), pipeline_run_id="bare-run-id"),
        )
        # Stand in for the real make_workflow_id, which prefixes by run mode. The bridge must report
        # THIS value (the id Temporal actually started the workflow under), not pipe_output.pipeline_run_id.
        temporal_pipe_run.make_workflow_id.return_value = "ut-bare-run-id"

        result = await run_pipe_via_bridge(
            PipelexPipeRunInput(pipe_code="fake_pipe", execution_mode=PipelexExecutionMode.TEMPORAL_BLOCKING),
        )

        temporal_pipe_run.make_workflow_id.assert_called_once_with(pipeline_run_id="bare-run-id")
        assert result.workflow_id == "ut-bare-run-id"
        assert result.workflow_id != result.pipeline_run_id
