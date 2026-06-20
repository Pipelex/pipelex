"""Gated real-inference cost test for split-worker (distributed) mode.

Every other split-worker usage test substitutes ``act_llm_gen_text`` with a
helper that hand-builds usage, so none of them prove that a *real* provider
response is captured, emitted through the runner fallback, and aggregated into a
non-zero cost total. Real distributed cost is otherwise validated only by manual
eyeballing. This test closes that blind spot end-to-end.

It is marked ``inference``/``llm`` so the default (no-spend) lanes skip it; run
it explicitly when validating real-inference cost capture in distributed mode.
The runner activity runs the genuine ``llm_gen_text`` — the real LLM call happens
on the runner queue and its usage report takes the per-process activity event log
unconditionally (in-activity emissions never touch a workflow's registered
context), just as a physically separate runner process would.
"""

import uuid
from collections.abc import Generator
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from temporalio import activity
from temporalio.client import Client as TemporalClient

from pipelex.cogt.content_generation.assignment_models import LLMAssignment
from pipelex.cogt.content_generation.llm_generate import llm_gen_text
from pipelex.cogt.usage.cost_registry import CostRegistry
from pipelex.cogt.usage.token_category import TokenCategory
from pipelex.config import get_config
from pipelex.pipe_run.pipe_job import PipeJob
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.system.configuration.config_temporal import ActivityRouteConfig
from pipelex.temporal.tprl_content_generation.act_llm_generate import act_llm_gen_text
from pipelex.temporal.tprl_pipe.wf_pipe_router import WfPipeRouter
from pipelex.tracing.ndjson_event_log import NdjsonEventLog
from pipelex.tracing.trace_events import UsageReportEvent
from pipelex.tracing.usage_aggregator import UsageAggregator
from tests.integration.pipelex.fixtures.pipe_job_helpers import pipe_job_from_bundle
from tests.integration.pipelex.temporal.library_crate.helpers import rehydrate_pipe_output
from tests.integration.pipelex.temporal.tracing.helpers import inject_trace_context, make_split_workers
from tests.integration.pipelex.temporal.tracing.test_data import SequenceTracingTestData

if TYPE_CHECKING:
    from pipelex.core.pipes.pipe_output import PipeOutput


@activity.defn(name="act_llm_gen_text")
async def _real_runner_act_llm_gen_text(llm_assignment: LLMAssignment) -> str:
    """Real-inference substitute: run the genuine LLM call from the activity.

    The synchronous usage report takes the per-process activity event log
    unconditionally — ``_emit_usage_event`` checks ``_is_in_temporal_activity()``
    before any context lookup, so the router's registered context (which lives in
    the same process during a single-process test) is never touched; ``llm_gen_text``
    performs the real provider call so the captured token counts are real.
    """
    return await llm_gen_text(llm_assignment=llm_assignment)


@pytest.mark.temporal
@pytest.mark.inference
@pytest.mark.llm
@pytest.mark.asyncio(loop_scope="class")
class TestSplitWorkerRealInferenceCost:
    """Real provider usage is captured, emitted via the runner fallback, and aggregated."""

    @pytest.fixture
    def split_queues(self) -> tuple[str, str]:
        return (f"q_router_{uuid.uuid4().hex[:8]}", f"q_runner_{uuid.uuid4().hex[:8]}")

    @pytest.fixture
    def live_sequence_tracing_job(self, is_class_registry_isolated: bool) -> Generator[PipeJob, None, None]:
        yield from pipe_job_from_bundle(
            bundle_file=SequenceTracingTestData.BUNDLE_FILE,
            pipe_code=SequenceTracingTestData.PIPE_CODE,
            pipe_run_mode=PipeRunMode.LIVE,
            isolated_registry=is_class_registry_isolated,
        )

    @pytest.fixture
    def route_llm_text_to_runner_queue(self, split_queues: tuple[str, str]) -> Generator[None, None, None]:
        _q_router, q_runner = split_queues
        worker_config = get_config().temporal.worker_config
        activity_name = act_llm_gen_text.__name__
        original_entry = worker_config.activity_queues.get(activity_name)
        worker_config.activity_queues[activity_name] = ActivityRouteConfig(default=q_runner, by_handle={})
        yield
        if original_entry is None:
            worker_config.activity_queues.pop(activity_name, None)
        else:
            worker_config.activity_queues[activity_name] = original_entry

    async def test_real_provider_usage_aggregates_to_nonzero_cost(
        self,
        live_sequence_tracing_job: PipeJob,
        temporal_client: TemporalClient,
        tracing_tmp_dir: Path,
        split_queues: tuple[str, str],
        route_llm_text_to_runner_queue: None,  # noqa: ARG002
    ) -> None:
        q_router, q_runner = split_queues
        execution_run_id = f"split_real_{uuid.uuid4().hex[:12]}"
        execution_job = inject_trace_context(live_sequence_tracing_job, execution_run_id)
        workflow_id = f"wf_{uuid.uuid4().hex[:12]}"

        async with make_split_workers(
            temporal_client,
            q_router=q_router,
            q_runner=q_runner,
            runner_act_llm_gen_text=_real_runner_act_llm_gen_text,
        ):
            pipe_output: PipeOutput = await temporal_client.execute_workflow(  # pyright: ignore[reportUnknownMemberType]
                workflow=WfPipeRouter.run,
                arg=execution_job,
                id=workflow_id,
                task_queue=q_router,
            )
        rehydrate_pipe_output(pipe_output)

        reader = NdjsonEventLog(traces_dir=str(tracing_tmp_dir))
        try:
            events = reader.read_events(execution_run_id)
        finally:
            reader.close()

        usage_events = [evt for evt in events if isinstance(evt, UsageReportEvent)]
        # The sequence bundle makes one real LLM call per step (step_one → step_two).
        assert len(usage_events) == 2, f"Expected one usage event per inference call, got {len(usage_events)}"
        assert all(evt.writer_id.startswith("act_") for evt in usage_events), "Runner fallback must have stamped act_* writer ids"

        tokens_usages = UsageAggregator.aggregate(events)
        assert all(
            tokens_usage.nb_tokens_by_category.get(TokenCategory.INPUT, 0) > 0 and tokens_usage.nb_tokens_by_category.get(TokenCategory.OUTPUT, 0) > 0
            for tokens_usage in tokens_usages
        ), "Real provider responses must carry non-zero input and output token counts"
        model_names = {tokens_usage.inference_model_name for tokens_usage in tokens_usages}
        assert all(model_names), "Every usage record must name its real model handle"

        aggregated = CostRegistry.aggregate_costs(tokens_usages=tokens_usages)
        assert aggregated.total_nb_tokens > 0
        assert aggregated.has_reportable_usage is True
