"""Temporal (cross-process) coverage for ``--mock-inference`` (Phase 5).

The DIRECT counterpart lives in
``tests/integration/pipelex/pipeline/test_mock_inference_direct.py``. This arm proves the part DIRECT
cannot: that ``JobMetadata.is_mock_inference`` survives the Temporal serialization boundary and the
**real** ``act_llm_gen_text`` activity honors it — faking the LLM at the cogt leaf inside the activity
body (no provider call), with the synthetic, reportable usage assembling back onto
``PipeOutput.tokens_usages`` via Step 2's ``act_assemble_tracing``.

Run LIVE (``PipeRunMode.LIVE``) so the workflow actually dispatches ``act_llm_gen_text`` (DRY would
swap ``ContentGeneratorDry`` in pre-dispatch and never reach the activity). The only thing faked is the
inference leaf, keyed on the per-run flag.

Like its sibling tracing tests this is ``gha_disabled`` by the directory conftest (the in-process
WorkflowEnvironment + concurrent pipe execution hangs under CI xdist); verify locally/serially.
"""

import uuid
from collections.abc import Generator
from typing import TYPE_CHECKING

import pytest
from temporalio.client import Client as TemporalClient

from pipelex.cogt.content_generation.dry_mock import MOCK_INFERENCE_MODEL_NAME
from pipelex.cogt.usage.cost_registry import CostRegistry
from pipelex.pipe_run.pipe_job import PipeJob
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.temporal.temporal_hub import get_task_manager
from pipelex.temporal.tprl_pipe.pipe_run_arg import PipeRunArg
from pipelex.temporal.tprl_pipe.wf_pipe_run import WfPipeRun
from tests.integration.pipelex.fixtures.pipe_job_helpers import pipe_job_from_bundle
from tests.integration.pipelex.temporal.library_crate.helpers import rehydrate_pipe_output
from tests.integration.pipelex.temporal.tracing.helpers import inject_trace_context
from tests.integration.pipelex.temporal.tracing.test_data import SequenceTracingTestData

if TYPE_CHECKING:
    from pipelex.core.pipes.pipe_output import PipeOutput


@pytest.mark.temporal
@pytest.mark.asyncio(loop_scope="class")
class TestTemporalMockInference:
    @pytest.fixture
    def mock_inference_sequence_job(self, is_class_registry_isolated: bool) -> Generator[PipeJob, None, None]:
        """A LIVE native_text_sequence job carrying is_mock_inference=True.

        LIVE forces the workflow to dispatch the real ``act_llm_gen_text``; the flag makes that
        activity's leaf fake the LLM. The same bundle is run LIVE (with a fake activity substitute)
        by ``test_split_worker_usage`` — here we run the *real* activity and let the flag do the mocking.
        """
        for pipe_job in pipe_job_from_bundle(
            bundle_file=SequenceTracingTestData.BUNDLE_FILE,
            pipe_code=SequenceTracingTestData.PIPE_CODE,
            pipe_run_mode=PipeRunMode.LIVE,
            isolated_registry=is_class_registry_isolated,
        ):
            yield pipe_job.model_copy(
                update={"job_metadata": pipe_job.job_metadata.model_copy(update={"is_mock_inference": True})},
            )

    async def test_mock_inference_assembles_reportable_usage_cross_process(
        self,
        mock_inference_sequence_job: PipeJob,
        temporal_client: TemporalClient,
    ) -> None:
        """The flag crosses the boundary, the real activity mocks the leaf, and reportable usage rides back."""
        execution_run_id = f"mock_inf_{uuid.uuid4().hex[:12]}"
        # costs-only (no graph) mirrors the realistic --no-graph --costs default the skill validates.
        execution_job = inject_trace_context(
            mock_inference_sequence_job,
            execution_run_id,
            emit_graph_events=False,
            emit_usage_events=True,
        )
        assert execution_job.job_metadata.is_mock_inference, "inject_trace_context must preserve is_mock_inference"

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
        rehydrate_pipe_output(pipe_output, pipe_job=mock_inference_sequence_job)

        assert pipe_output.tokens_usages is not None
        assert len(pipe_output.tokens_usages) >= 1
        # All usage came from the mocked leaf (the sentinel model) — proof no real provider ran.
        assert all(usage.inference_model_name == MOCK_INFERENCE_MODEL_NAME for usage in pipe_output.tokens_usages)
        # Non-zero synthetic usage -> a cost report would render (not suppressed like a dry run).
        assert CostRegistry.aggregate_costs(pipe_output.tokens_usages).has_reportable_usage
