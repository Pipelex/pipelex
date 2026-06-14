"""Temporal arm of the local / Temporal ``ErrorReport`` parity pair for web search.

Runs the ``native_search`` pipe through a real ``WfPipeRouter`` workflow on the in-process Temporal
server, submitted via ``WorkflowExecutor.execute_workflow``, with the activity-side search call mocked to
fail. This is the regression test for the original bug: before ``PipeSearch`` routed its leaf through a
Temporal activity, a search failure raised a raw ``SearchJobFailureError`` inside the workflow, which was
neither an ``ActivityError`` nor a ``WorkflowExecutionError`` — so Temporal retried the workflow task
forever and the submitter hung. Now the failure crosses the activity → workflow → submitter boundary as a
terminal ``WorkflowExecutionError`` carrying the structured ``ErrorReport``.

The local baseline is the separate module
``tests/integration/pipelex/error_handling/test_search_error_report_local_full_chain.py``; both arms assert
the same ``SearchErrorReportParityTestData`` constants, so local / Temporal parity holds by construction.
"""

import uuid
from collections.abc import Generator
from typing import TYPE_CHECKING

import pytest
from pytest_mock import MockerFixture
from temporalio.client import Client as TemporalClient
from temporalio.common import RetryPolicy

from pipelex.config import get_config
from pipelex.pipe_run.pipe_job import PipeJob
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.temporal.exceptions import WorkflowExecutionError
from pipelex.temporal.temporal_hub import get_task_manager
from pipelex.temporal.tprl.workflow_caller import WorkflowExecutor
from pipelex.temporal.tprl_pipe.wf_pipe_router import WfPipeRouter
from tests.integration.pipelex.error_handling.test_data import SearchErrorReportParityTestData
from tests.integration.pipelex.fixtures.pipe_job_helpers import pipe_job_from_bundle

if TYPE_CHECKING:
    from pipelex.core.pipes.pipe_output import PipeOutput

ACT_SEARCH_SOURCED_ANSWER_TARGET = "pipelex.temporal.tprl_content_generation.act_search_generate.search_gen_sourced_answer"


@pytest.mark.temporal
@pytest.mark.asyncio(loop_scope="class")
class TestWorkflowSearchErrorReportFullChain:
    """A failing search pipe's structured ``ErrorReport`` survives the Temporal workflow → submitter boundary."""

    @pytest.fixture
    def temporal_enabled(self) -> Generator[None, None, None]:
        """Enable ``temporal.is_enabled`` for the test — ``WorkflowExecutor.temporal_client()`` raises when off."""
        config = get_config()
        previous = config.temporal.is_enabled
        config.temporal = config.temporal.model_copy(update={"is_enabled": True})
        yield
        config.temporal = config.temporal.model_copy(update={"is_enabled": previous})

    @pytest.fixture
    def failing_search_pipe_job(self) -> Generator[PipeJob, None, None]:
        """A PipeJob for the search pipe, in LIVE mode so the workflow dispatches the search activity.

        DRY mode short-circuits the ``act_search_*`` dispatch (the dry content generator reports inline
        inside the workflow), so the activity — and the mock — never fire.
        """
        yield from pipe_job_from_bundle(
            bundle_file=SearchErrorReportParityTestData.BUNDLE_FILE,
            pipe_code=SearchErrorReportParityTestData.PIPE_CODE,
            pipe_run_mode=PipeRunMode.LIVE,
        )

    async def test_search_error_report_survives_temporal_boundary(
        self,
        temporal_client: TemporalClient,
        mocker: MockerFixture,
        temporal_enabled: None,  # noqa: ARG002 - enables temporal.is_enabled for the duration
        failing_search_pipe_job: PipeJob,
    ) -> None:
        """A failing search run through Temporal surfaces a fully classified ``WorkflowExecutionError`` (no hang)."""
        # Mock the search core inside the real activity (in-process unsandboxed worker, same process).
        # @convert_pipelex_errors packs the ErrorReport into ApplicationError.details.
        mocker.patch(
            ACT_SEARCH_SOURCED_ANSWER_TARGET,
            new=mocker.AsyncMock(side_effect=SearchErrorReportParityTestData.make_failing_search_error()),
        )

        task_queue = f"q_search_err_{uuid.uuid4().hex[:8]}"
        workflow_id = f"wf_search_err_{uuid.uuid4().hex[:8]}"
        executor: WorkflowExecutor[PipeJob, PipeOutput] = WorkflowExecutor(
            temporal_client=temporal_client,
            task_queue=task_queue,
            retry_policy=RetryPolicy(maximum_attempts=1),
        )

        async with get_task_manager().make_worker(temporal_client, task_queue=task_queue, is_not_sandboxed=True):
            with pytest.raises(WorkflowExecutionError) as exc_info:
                await executor.execute_workflow(
                    workflow_class=WfPipeRouter,
                    workflow_arg=failing_search_pipe_job,
                    workflow_id=workflow_id,
                )

        error = exc_info.value
        # The structured report was recovered across the workflow → submitter boundary.
        assert error.error_report is not None
        report = error.to_error_report()

        # The real failure message survived — not the generic "Failed to execute workflow ...".
        assert SearchErrorReportParityTestData.FAILURE_MESSAGE in report.message
        assert "Failed to execute workflow" not in report.message

        # The full classification survived the Temporal serialization round-trip.
        assert report.error_category == SearchErrorReportParityTestData.FAILURE_CATEGORY
        assert report.retryable == SearchErrorReportParityTestData.EXPECTED_RETRYABLE
        assert report.model == SearchErrorReportParityTestData.FAILURE_MODEL
        assert report.provider == SearchErrorReportParityTestData.FAILURE_PROVIDER
        assert report.user_action is not None
        assert report.user_action.kind == SearchErrorReportParityTestData.EXPECTED_USER_ACTION_KIND
