"""Mode-1 companion of Tier 17: DRY honors the Temporal backend (Part B, req 1).

The default-dry analogue of ``test_mock_usage_temporal.py``. Pre-Part-B, a Temporal dry run never
dispatched ``act_llm_gen_*`` (operators swapped in a workflow-side dry generator); after Part B,
``run_mode=DRY`` rides ``CogtRunParams`` across the serialization boundary, the workflow dispatches
the REAL ``act_llm_gen_text`` activity, and the cogt leaf mocks INSIDE the activity — zero-token
synthetic usage (cost report suppressed by design), no provider call.

The dispatch assertion reads the workflow history (``ActivityTaskScheduled`` across the parent and
its child workflows), which is the same signal the Mode-2 / Tier 17 e2e arm checks against a real
Temporal server. Lives under ``tracing/`` so the directory conftest applies both the CI quarantine
(in-process WorkflowEnvironment + child workflows hang under CI xdist) and the tmp-dir trace
redirect (usage assembly must not write to the configured traces backend).
"""

import uuid
from collections.abc import Generator
from typing import TYPE_CHECKING

import pytest
from temporalio.client import Client as TemporalClient

from pipelex.cogt.content_generation.dry_mock import DRY_RUN_INFERENCE_MODEL_NAME
from pipelex.cogt.usage.cost_registry import CostRegistry
from pipelex.pipe_run.pipe_job import PipeJob
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.runtime_bridge.primitives.pipe_run_arg import PipeRunArg
from pipelex.temporal.temporal_hub import get_task_manager
from pipelex.temporal.tprl_content_generation.act_llm_generate import act_llm_gen_text
from pipelex.temporal.tprl_pipe.wf_pipe_run import WfPipeRun
from tests.integration.pipelex.fixtures.pipe_job_helpers import pipe_job_from_bundle
from tests.integration.pipelex.temporal.library_crate.helpers import rehydrate_pipe_output
from tests.integration.pipelex.temporal.tracing.helpers import collect_scheduled_activity_counts, inject_trace_context
from tests.integration.pipelex.temporal.tracing.test_data import SequenceTracingTestData

if TYPE_CHECKING:
    from pipelex.core.pipes.pipe_output import PipeOutput

# native_text_sequence is a two-step PipeSequence of PipeLLMs: each step must dispatch its own
# act_llm_gen_text and report its own (zero-token) usage — a single dispatch would mean one step
# silently bypassed the distribution machinery.
EXPECTED_LLM_DISPATCHES = 2


@pytest.mark.temporal
@pytest.mark.asyncio(loop_scope="class")
class TestTemporalDryRunDispatchesAndMocks:
    @pytest.fixture
    def dry_sequence_job(self, is_class_registry_isolated: bool) -> Generator[PipeJob, None, None]:
        """A DRY native_text_sequence job — same bundle as the mock-usage arm, default dry reporting."""
        yield from pipe_job_from_bundle(
            bundle_file=SequenceTracingTestData.BUNDLE_FILE,
            pipe_code=SequenceTracingTestData.PIPE_CODE,
            pipe_run_mode=PipeRunMode.DRY,
            isolated_registry=is_class_registry_isolated,
        )

    async def test_dry_run_dispatches_activities_and_mocks_inside(
        self,
        dry_sequence_job: PipeJob,
        temporal_client: TemporalClient,
    ) -> None:
        """DRY dispatches the real act_llm_gen_* and the leaf mocks inside, zero-token suppressed."""
        execution_run_id = f"dry_dispatch_{uuid.uuid4().hex[:12]}"
        execution_job = inject_trace_context(
            dry_sequence_job,
            execution_run_id,
            emit_graph_events=False,
            emit_usage_events=True,
        )
        assert execution_job.pipe_run_params.run_mode.is_dry, "inject_trace_context must preserve run_mode"

        pipe_run_arg = PipeRunArg(pipe_job=execution_job).prepare_for_temporal()
        task_queue = str(uuid.uuid4())
        workflow_id = str(uuid.uuid4())

        async with get_task_manager().make_worker(temporal_client, task_queue=task_queue, is_not_sandboxed=True):
            workflow_handle = await temporal_client.start_workflow(  # pyright: ignore[reportUnknownMemberType]
                workflow=WfPipeRun.run,
                arg=pipe_run_arg,
                id=workflow_id,
                task_queue=task_queue,
            )
            pipe_output: PipeOutput = await workflow_handle.result()
            # The LLM activity is scheduled by the controller's CHILD workflows (one per step), so
            # count ActivityTaskScheduled events across the whole workflow tree.
            scheduled_counts = await collect_scheduled_activity_counts(temporal_client, workflow_id)

        # THE req-1 flip: the dry run DID dispatch the LLM activity, once per sequence step
        # (pre-Part-B it dispatched nothing inference-related).
        assert scheduled_counts[act_llm_gen_text.__name__] == EXPECTED_LLM_DISPATCHES

        rehydrate_pipe_output(pipe_output, pipe_job=dry_sequence_job)

        # The leaf mocked INSIDE the activity: the output is the DRY mock, not provider text.
        assert "DRY RUN:" in pipe_output.main_stuff_as_text.text

        # One zero-token usage per step under the dry_run sentinel — assembled back cross-process,
        # but the cost report stays suppressed (the inverse of is_mock_usage's reportable payload).
        assert pipe_output.tokens_usages is not None
        assert len(pipe_output.tokens_usages) == EXPECTED_LLM_DISPATCHES
        assert all(usage.inference_model_name == DRY_RUN_INFERENCE_MODEL_NAME for usage in pipe_output.tokens_usages)
        assert not CostRegistry.aggregate_costs(pipe_output.tokens_usages).has_reportable_usage
