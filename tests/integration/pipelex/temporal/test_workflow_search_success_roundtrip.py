"""Success-path counterpart to the search error-report full-chain test.

Runs the ``native_search`` pipe through a real ``WfPipeRouter`` workflow on the in-process Temporal server
with the activity-side search call mocked to *succeed*, and asserts the ``SearchResultContent`` comes back
intact across the activity → workflow → submitter boundary. This locks in the other half of the fix: search
on Temporal now records its result via an activity (replay-safe) instead of running inline on the workflow
loop, and the native ``SearchResultContent`` serializes cleanly back to the submitter. The mock firing also
proves the workflow actually dispatched ``act_search_gen_sourced_answer`` rather than running the leaf inline.
"""

import uuid
from collections.abc import Generator
from typing import TYPE_CHECKING

import pytest
from pytest_mock import MockerFixture
from temporalio.client import Client as TemporalClient
from temporalio.common import RetryPolicy

from pipelex.config import get_config
from pipelex.core.stuffs.document_content import DocumentContent
from pipelex.core.stuffs.search_result_content import SearchResultContent
from pipelex.pipe_run.pipe_job import PipeJob
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.temporal.temporal_hub import get_task_manager
from pipelex.temporal.tprl.workflow_caller import WorkflowExecutor
from pipelex.temporal.tprl_pipe.wf_pipe_router import WfPipeRouter
from tests.integration.pipelex.error_handling.test_data import SearchErrorReportParityTestData
from tests.integration.pipelex.fixtures.pipe_job_helpers import pipe_job_from_bundle
from tests.integration.pipelex.temporal.library_crate.helpers import rehydrate_pipe_output

if TYPE_CHECKING:
    from pipelex.core.pipes.pipe_output import PipeOutput

ACT_SEARCH_SOURCED_ANSWER_TARGET = "pipelex.temporal.tprl_content_generation.act_search_generate.search_gen_sourced_answer"

EXPECTED_ANSWER = "Recent AI safety work focuses on interpretability and scalable oversight."
EXPECTED_SOURCE_TITLE = "AI safety overview"


@pytest.mark.temporal
@pytest.mark.asyncio(loop_scope="class")
class TestWorkflowSearchSuccessRoundtrip:
    """A successful search result survives the Temporal activity → workflow → submitter round-trip."""

    @pytest.fixture
    def temporal_enabled(self) -> Generator[None, None, None]:
        config = get_config()
        previous = config.temporal.is_enabled
        config.temporal = config.temporal.model_copy(update={"is_enabled": True})
        yield
        config.temporal = config.temporal.model_copy(update={"is_enabled": previous})

    @pytest.fixture
    def search_pipe_job(self) -> Generator[PipeJob, None, None]:
        """A PipeJob for the search pipe, in LIVE mode so the workflow dispatches the search activity."""
        yield from pipe_job_from_bundle(
            bundle_file=SearchErrorReportParityTestData.BUNDLE_FILE,
            pipe_code=SearchErrorReportParityTestData.PIPE_CODE,
            pipe_run_mode=PipeRunMode.LIVE,
        )

    async def test_search_result_survives_temporal_boundary(
        self,
        temporal_client: TemporalClient,
        mocker: MockerFixture,
        temporal_enabled: None,  # noqa: ARG002 - enables temporal.is_enabled for the duration
        search_pipe_job: PipeJob,
    ) -> None:
        """The activity's ``SearchResultContent`` comes back intact on the submitter's ``PipeOutput``."""
        mock_result = SearchResultContent(
            answer=EXPECTED_ANSWER,
            sources=[DocumentContent(title=EXPECTED_SOURCE_TITLE, url="https://example.com/ai-safety", mime_type="text/html")],
        )
        search_core_mock = mocker.AsyncMock(return_value=mock_result)
        mocker.patch(ACT_SEARCH_SOURCED_ANSWER_TARGET, new=search_core_mock)

        task_queue = f"q_search_ok_{uuid.uuid4().hex[:8]}"
        workflow_id = f"wf_search_ok_{uuid.uuid4().hex[:8]}"
        executor: WorkflowExecutor[PipeJob, PipeOutput] = WorkflowExecutor(
            temporal_client=temporal_client,
            task_queue=task_queue,
            retry_policy=RetryPolicy(maximum_attempts=1),
        )

        async with get_task_manager().make_worker(temporal_client, task_queue=task_queue, is_not_sandboxed=True):
            pipe_output = await executor.execute_workflow(
                workflow_class=WfPipeRouter,
                workflow_arg=search_pipe_job,
                workflow_id=workflow_id,
            )

        # The activity dispatched (mock fired) — the leaf did not run inline in the workflow.
        search_core_mock.assert_awaited_once()

        # The SearchResultContent round-tripped back to the submitter intact (rehydrate the deferred
        # working memory exactly as a production submitter does).
        rehydrate_pipe_output(pipe_output, search_pipe_job)
        content = pipe_output.main_stuff.content
        assert isinstance(content, SearchResultContent)
        assert content.answer == EXPECTED_ANSWER
        assert len(content.sources) == 1
        assert content.sources[0].title == EXPECTED_SOURCE_TITLE
