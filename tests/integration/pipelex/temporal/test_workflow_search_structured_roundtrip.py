"""Structured-output counterpart to the search success round-trip test.

Runs a ``PipeSearch`` step whose output is a *custom structured concept* (``TopicSummary``) through a real
``WfPipeRouter`` workflow on the in-process Temporal server, with the activity-side search call mocked to
*succeed*. This exercises the ``act_search_gen_structured`` path — the riskier of the two search activities:
the operator ships the output structure's JSON schema (not the live class) across the boundary via
``SearchObjectAssignment``, the activity reconstructs a throwaway class to drive the provider and returns the
**raw result dict**, and the submitter re-validates that dict against the original output class
(``output_structure_class.model_validate(result_dict)``) — a pure, deterministic step that keeps the dynamic
class on the submitter side. This test locks in that whole round-trip; the sourced-answer sibling
(``test_workflow_search_success_roundtrip.py``) covers the non-structured path. The mock firing also proves the
workflow dispatched ``act_search_gen_structured`` rather than running the leaf inline on the workflow loop.
"""

import uuid
from collections.abc import Generator
from typing import TYPE_CHECKING

import pytest
from pytest_mock import MockerFixture
from temporalio.client import Client as TemporalClient
from temporalio.common import RetryPolicy

from pipelex.config import get_config
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.pipe_run.pipe_job import PipeJob
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.temporal.temporal_hub import get_task_manager
from pipelex.temporal.tprl.workflow_caller import WorkflowExecutor
from pipelex.temporal.tprl_pipe.wf_pipe_router import WfPipeRouter
from tests.integration.pipelex.fixtures.pipe_job_helpers import pipe_job_from_bundle
from tests.integration.pipelex.temporal.library_crate.helpers import rehydrate_pipe_output

if TYPE_CHECKING:
    from pipelex.core.pipes.pipe_output import PipeOutput

ACT_SEARCH_STRUCTURED_TARGET = "pipelex.temporal.tprl_content_generation.act_search_generate.search_gen_structured"

BUNDLE_FILE = "tests/integration/pipelex/temporal/library_crate/structured_search.mthds"
PIPE_CODE = "structured_search"

# Flat, schema-shaped dict — matches what the real worker returns (LinkupSearchWorker._search_structured
# returns response.model_dump()), which the submitter re-validates against the TopicSummary structure class.
EXPECTED_TITLE = "AI safety in 2026"
EXPECTED_SUMMARY = "Interpretability and scalable oversight lead the agenda."
EXPECTED_KEY_POINTS = ["Mechanistic interpretability", "Scalable oversight"]


@pytest.mark.temporal
@pytest.mark.asyncio(loop_scope="class")
class TestWorkflowSearchStructuredRoundtrip:
    """A structured search result survives the Temporal activity → workflow → submitter round-trip."""

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

    async def test_structured_search_result_survives_temporal_boundary(
        self,
        temporal_client: TemporalClient,
        mocker: MockerFixture,
        temporal_enabled: None,  # noqa: ARG002 - enables temporal.is_enabled for the duration
        structured_search_pipe_job: PipeJob,
    ) -> None:
        """The activity's raw dict re-validates into the TopicSummary structure class on the submitter, intact."""
        mock_result = {
            "title": EXPECTED_TITLE,
            "summary": EXPECTED_SUMMARY,
            "key_points": EXPECTED_KEY_POINTS,
        }
        search_core_mock = mocker.AsyncMock(return_value=mock_result)
        mocker.patch(ACT_SEARCH_STRUCTURED_TARGET, new=search_core_mock)

        task_queue = f"q_search_struct_{uuid.uuid4().hex[:8]}"
        workflow_id = f"wf_search_struct_{uuid.uuid4().hex[:8]}"
        executor: WorkflowExecutor[PipeJob, PipeOutput] = WorkflowExecutor(
            temporal_client=temporal_client,
            task_queue=task_queue,
            retry_policy=RetryPolicy(maximum_attempts=1),
        )

        async with get_task_manager().make_worker(temporal_client, task_queue=task_queue, is_not_sandboxed=True):
            pipe_output = await executor.execute_workflow(
                workflow_class=WfPipeRouter,
                workflow_arg=structured_search_pipe_job,
                workflow_id=workflow_id,
            )

        # The structured activity dispatched (mock fired) — the leaf did not run inline in the workflow,
        # and the SearchObjectAssignment (carrying output_class_schema) crossed the boundary.
        search_core_mock.assert_awaited_once()

        # The raw dict re-validated against the original output class on the submitter side and round-tripped
        # intact (rehydrate the deferred working memory exactly as a production submitter does).
        rehydrate_pipe_output(pipe_output, structured_search_pipe_job)
        content = pipe_output.main_stuff.content
        assert isinstance(content, StructuredContent)
        data = content.model_dump()
        assert data["title"] == EXPECTED_TITLE
        assert data["summary"] == EXPECTED_SUMMARY
        assert data["key_points"] == EXPECTED_KEY_POINTS
