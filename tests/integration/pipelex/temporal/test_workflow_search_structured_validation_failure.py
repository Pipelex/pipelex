"""Regression test: a malformed structured-search result fails the Temporal workflow terminally, not a hang.

The structured-search activity (``act_search_gen_structured``) returns the provider's *raw* result dict — the
gateway worker returns ``json.loads(...)`` unvalidated against the schema — and the submitter re-validates it
against the original output structure class with ``output_structure_class.model_validate(result_dict)`` in
workflow code, *outside* the activity's ``convert_pipelex_errors`` boundary. Left to raise a bare
``pydantic.ValidationError`` there, it would be neither a ``WorkflowExecutionError`` nor a ``PipelexError`` — the
only two ``workflow_failure_exception_types`` — so Temporal would treat it as a *workflow-task* failure and retry
indefinitely, hanging the submitter (the exact failure mode the whole search seam exists to prevent).
``make_search_structured`` converts it to a terminal ``ContentGenerationError`` (a ``PipelexError``) instead; this
test locks that in by feeding a malformed dict and asserting the submitter gets a terminal
``WorkflowExecutionError`` rather than hanging. The success sibling is ``test_workflow_search_structured_roundtrip.py``.
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
from tests.integration.pipelex.fixtures.pipe_job_helpers import pipe_job_from_bundle

if TYPE_CHECKING:
    from pipelex.core.pipes.pipe_output import PipeOutput

ACT_SEARCH_STRUCTURED_TARGET = "pipelex.temporal.tprl_content_generation.act_search_generate.search_gen_structured"

BUNDLE_FILE = "tests/integration/pipelex/temporal/library_crate/structured_search.mthds"
PIPE_CODE = "structured_search"

# A dict the provider could plausibly return that does NOT satisfy the TopicSummary structure: the required
# ``title`` field is missing, so re-validating it against the original output class on the submitter must fail.
MALFORMED_RESULT = {
    "summary": "Interpretability and scalable oversight lead the agenda.",
    "key_points": ["Mechanistic interpretability", "Scalable oversight"],
}


@pytest.mark.temporal
@pytest.mark.asyncio(loop_scope="class")
class TestWorkflowSearchStructuredValidationFailure:
    """A malformed structured-search result surfaces a terminal WorkflowExecutionError instead of hanging."""

    @pytest.fixture
    def temporal_enabled(self) -> Generator[None, None, None]:
        config = get_config()
        previous = config.temporal.is_enabled
        config.temporal = config.temporal.model_copy(update={"is_enabled": True})
        yield
        config.temporal = config.temporal.model_copy(update={"is_enabled": previous})

    @pytest.fixture
    def structured_search_pipe_job(self) -> Generator[PipeJob, None, None]:
        """A PipeJob for the structured search pipe, in LIVE mode so the workflow dispatches the search activity."""
        yield from pipe_job_from_bundle(
            bundle_file=BUNDLE_FILE,
            pipe_code=PIPE_CODE,
            pipe_run_mode=PipeRunMode.LIVE,
        )

    @pytest.mark.timeout(60)
    async def test_malformed_structured_result_fails_terminally(
        self,
        temporal_client: TemporalClient,
        mocker: MockerFixture,
        temporal_enabled: None,  # noqa: ARG002 - enables temporal.is_enabled for the duration
        structured_search_pipe_job: PipeJob,
    ) -> None:
        """A structured-search dict that fails submitter-side re-validation terminates the workflow, not hangs."""
        search_core_mock = mocker.AsyncMock(return_value=MALFORMED_RESULT)
        mocker.patch(ACT_SEARCH_STRUCTURED_TARGET, new=search_core_mock)

        task_queue = f"q_search_struct_bad_{uuid.uuid4().hex[:8]}"
        workflow_id = f"wf_search_struct_bad_{uuid.uuid4().hex[:8]}"
        executor: WorkflowExecutor[PipeJob, PipeOutput] = WorkflowExecutor(
            temporal_client=temporal_client,
            task_queue=task_queue,
            retry_policy=RetryPolicy(maximum_attempts=1),
        )

        async with get_task_manager().make_worker(temporal_client, task_queue=task_queue, is_not_sandboxed=True):
            with pytest.raises(WorkflowExecutionError) as exc_info:
                await executor.execute_workflow(
                    workflow_class=WfPipeRouter,
                    workflow_arg=structured_search_pipe_job,
                    workflow_id=workflow_id,
                )

        # The structured activity dispatched (mock fired) — the malformed dict came back through the boundary,
        # and the failure happened on the submitter side, not inside the (successful) activity.
        search_core_mock.assert_awaited_once()

        # Terminal failure, not a hang: the submitter recovered a structured report whose message reflects the
        # submitter-side structured-validation failure (not a generic "Failed to execute workflow ...").
        error = exc_info.value
        assert error.error_report is not None
        report = error.to_error_report()
        assert "validation" in report.message.lower()
        assert "Failed to execute workflow" not in report.message
