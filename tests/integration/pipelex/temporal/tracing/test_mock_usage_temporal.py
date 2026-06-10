"""Temporal (cross-process) coverage for the ``is_mock_usage`` dry sub-flag.

The DIRECT counterpart lives in
``tests/integration/pipelex/pipeline/test_mock_usage_direct.py``. This arm proves the part DIRECT
cannot: that ``CogtRunParams.is_mock_usage`` survives the Temporal serialization boundary and the
**real** ``act_llm_gen_text`` activity honors it — the dry leaf inside the activity body selects the
non-zero reporting payload (no provider call), with the synthetic, reportable usage assembling back
onto ``PipeOutput.tokens_usages`` via Step 2's ``act_assemble_tracing``.

Run DRY (the flag is a sub-flag of DRY): the workflow still dispatches the real activity tree
(run mode is orthogonal to backend — Tier 17), and ``is_mock_usage`` flips the leaf reporting from
the suppressed zero-token payload to the reportable non-zero one.

Like its sibling tracing tests this is ``gha_disabled`` by the directory conftest (the in-process
WorkflowEnvironment + concurrent pipe execution hangs under CI xdist); verify locally/serially.
"""

import uuid
from collections.abc import Generator
from typing import TYPE_CHECKING

import pytest
from temporalio.client import Client as TemporalClient

from pipelex.cogt.content_generation.dry_mock import MOCK_USAGE_MODEL_NAME
from pipelex.cogt.usage.cost_registry import CostRegistry
from pipelex.pipe_run.pipe_job import PipeJob
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.runtime_bridge.primitives.pipe_run_arg import PipeRunArg
from pipelex.temporal.temporal_hub import get_task_manager
from pipelex.temporal.tprl_pipe.wf_pipe_run import WfPipeRun
from tests.integration.pipelex.fixtures.pipe_job_helpers import pipe_job_from_bundle
from tests.integration.pipelex.temporal.library_crate.helpers import rehydrate_pipe_output
from tests.integration.pipelex.temporal.tracing.helpers import inject_trace_context
from tests.integration.pipelex.temporal.tracing.test_data import SequenceTracingTestData

if TYPE_CHECKING:
    from pipelex.core.pipes.pipe_output import PipeOutput


@pytest.mark.temporal
@pytest.mark.asyncio(loop_scope="class")
class TestTemporalMockUsage:
    @pytest.fixture
    def mock_usage_sequence_job(self, is_class_registry_isolated: bool) -> Generator[PipeJob, None, None]:
        """A DRY native_text_sequence job carrying is_mock_usage=True.

        DRY still dispatches the real ``act_llm_gen_text`` (run mode orthogonal to backend); the
        flag makes that activity's leaf report non-zero synthetic usage instead of the suppressed
        zero-token payload.
        """
        for pipe_job in pipe_job_from_bundle(
            bundle_file=SequenceTracingTestData.BUNDLE_FILE,
            pipe_code=SequenceTracingTestData.PIPE_CODE,
            pipe_run_mode=PipeRunMode.DRY,
            isolated_registry=is_class_registry_isolated,
        ):
            mocked_run_params = pipe_job.pipe_run_params.model_copy(update={"is_mock_usage": True})
            yield pipe_job.model_copy(update={"pipe_run_params": mocked_run_params})

    async def test_mock_usage_assembles_reportable_usage_cross_process(
        self,
        mock_usage_sequence_job: PipeJob,
        temporal_client: TemporalClient,
    ) -> None:
        """The flag crosses the boundary, the real activity honors it, and reportable usage rides back."""
        execution_run_id = f"mock_usage_{uuid.uuid4().hex[:12]}"
        # costs-only (no graph) mirrors the realistic --no-graph --costs default the skill validates.
        execution_job = inject_trace_context(
            mock_usage_sequence_job,
            execution_run_id,
            emit_graph_events=False,
            emit_usage_events=True,
        )
        assert execution_job.pipe_run_params.cogt_run_params.is_mock_usage, "inject_trace_context must preserve is_mock_usage"

        pipe_run_arg = PipeRunArg(pipe_job=execution_job).prepare_for_temporal()
        task_queue = str(uuid.uuid4())
        workflow_id = str(uuid.uuid4())

        async with get_task_manager().make_worker(temporal_client, task_queue=task_queue, is_not_sandboxed=True):
            pipe_output: PipeOutput = await temporal_client.execute_workflow(  # pyright: ignore[reportUnknownMemberType]
                workflow=WfPipeRun.run,
                arg=pipe_run_arg,
                id=workflow_id,
                task_queue=task_queue,
            )
        rehydrate_pipe_output(pipe_output, pipe_job=mock_usage_sequence_job)

        assert pipe_output.tokens_usages is not None
        assert len(pipe_output.tokens_usages) >= 1
        # All usage came from the mocked leaf (the sentinel model) — proof no real provider ran.
        assert all(usage.inference_model_name == MOCK_USAGE_MODEL_NAME for usage in pipe_output.tokens_usages)
        # Non-zero synthetic usage -> a cost report would render (not suppressed like a default dry run).
        assert CostRegistry.aggregate_costs(pipe_output.tokens_usages).has_reportable_usage
