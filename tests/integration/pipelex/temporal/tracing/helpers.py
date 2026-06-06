"""Shared test helpers for Temporal graph tracing integration tests."""

import uuid
from collections import defaultdict
from collections.abc import AsyncGenerator, Generator, Iterable
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime
from pathlib import Path

from temporalio import activity
from temporalio.client import Client as TemporalClient

from pipelex.cogt.content_generation.assignment_models import LLMAssignment
from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.cogt.llm.llm_job_components import LLMJobConfig, LLMJobReport
from pipelex.cogt.llm.llm_report import LLMTokensUsage
from pipelex.cogt.usage.cost_category import CostCategory
from pipelex.cogt.usage.token_category import TokenCategory
from pipelex.config import get_config
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.graph.graph_config import DataInclusionConfig
from pipelex.graph.graph_context import GraphContext
from pipelex.graph.graphspec import EdgeKind, EdgeSpec, GraphSpec, NodeStatus, PipelineRef
from pipelex.hub import get_report_delegate
from pipelex.pipe_run.pipe_job import PipeJob
from pipelex.reporting.reporting_manager import ReportingManager
from pipelex.temporal.config_temporal import ActivityRouteConfig
from pipelex.temporal.temporal_hub import get_task_manager
from pipelex.temporal.tprl_content_generation.act_llm_generate import act_llm_gen_text
from pipelex.temporal.tprl_pipe.wf_pipe_router import WfPipeRouter
from pipelex.tracing.graphspec_assembler import GraphSpecAssembler
from pipelex.tracing.ndjson_event_log import NdjsonEventLog
from tests.integration.pipelex.temporal.library_crate.helpers import rehydrate_pipe_output


@contextmanager
def route_activities_to(queue: str, activity_names: Iterable[str]) -> Generator[None, None, None]:
    """Temporarily route the given activity names to ``queue`` via
    ``worker_config.activity_queues``, restoring prior entries on exit.

    Tests that run an in-process worker on a UUID-based task queue and
    substitute activities on that worker need this override: without it the
    in-workflow dispatcher resolves to ``worker_config.default_task_queue``
    (the production default) where no worker is listening, and the activity
    hangs until pytest-timeout fires.
    """
    worker_config = get_config().temporal.worker_config
    originals: dict[str, ActivityRouteConfig | None] = {}
    for activity_name in activity_names:
        originals[activity_name] = worker_config.activity_queues.get(activity_name)
        worker_config.activity_queues[activity_name] = ActivityRouteConfig(default=queue, by_handle={})
    try:
        yield
    finally:
        for activity_name, original in originals.items():
            if original is None:
                worker_config.activity_queues.pop(activity_name, None)
            else:
                worker_config.activity_queues[activity_name] = original


def inject_graph_context(pipe_job: PipeJob, pipeline_run_id: str) -> PipeJob:
    """Deep-copy a PipeJob and inject a GraphContext onto its JobMetadata.

    Also overrides pipeline_run_id (must not be the dry-run sentinel,
    since NdjsonEventLog uses it as a directory name).
    """
    graph_context = GraphContext(
        graph_id=pipeline_run_id,
        parent_node_id=None,
        node_sequence=0,
        data_inclusion=DataInclusionConfig(
            pipe_and_concept_registry=True,
            stuff_json_content=False,
            stuff_text_content=False,
            stuff_html_content=False,
            error_stack_traces=False,
        ),
    )
    new_metadata = pipe_job.job_metadata.model_copy(
        update={
            "graph_context": graph_context,
            "pipeline_run_id": pipeline_run_id,
        },
    )
    return pipe_job.model_copy(update={"job_metadata": new_metadata})


class TracingResult:
    """Result of a traced workflow execution."""

    def __init__(self, pipe_output: PipeOutput, graph_spec: GraphSpec | None, pipeline_run_id: str) -> None:
        self.pipe_output = pipe_output
        self.graph_spec = graph_spec
        self.pipeline_run_id = pipeline_run_id


async def execute_and_assemble(
    pipe_job: PipeJob,
    temporal_client: TemporalClient,
    traces_dir: str,
) -> TracingResult:
    """Execute a workflow on Temporal and assemble a GraphSpec from emitted events.

    Each call uses a unique pipeline_run_id to isolate NDJSON files across calls.

    Returns:
        TracingResult with pipe_output, graph_spec, and pipeline_run_id.
    """
    # Give each execution its own pipeline_run_id to avoid event accumulation
    execution_run_id = f"tracing_exec_{uuid.uuid4().hex[:12]}"
    execution_job = inject_graph_context(pipe_job, execution_run_id)

    task_queue = str(uuid.uuid4())
    workflow_id = str(uuid.uuid4())

    async with get_task_manager().make_worker(
        temporal_client,
        task_queue=task_queue,
        is_not_sandboxed=True,
    ):
        pipe_output: PipeOutput = await temporal_client.execute_workflow(  # pyright: ignore[reportUnknownMemberType]
            workflow=WfPipeRouter.run,
            arg=execution_job,
            id=workflow_id,
            task_queue=task_queue,
        )

    rehydrate_pipe_output(pipe_output)

    # Read events and assemble GraphSpec
    event_log = NdjsonEventLog(traces_dir=traces_dir)
    try:
        events = event_log.read_events(execution_run_id)
    finally:
        event_log.close()

    if not events:
        return TracingResult(pipe_output=pipe_output, graph_spec=None, pipeline_run_id=execution_run_id)

    domain = pipe_job.pipe.domain_code
    main_pipe = pipe_job.pipe.code
    graph_spec = GraphSpecAssembler.assemble(
        events=events,
        graph_id=execution_run_id,
        pipeline_ref=PipelineRef(domain=domain, main_pipe=main_pipe),
    )
    return TracingResult(pipe_output=pipe_output, graph_spec=graph_spec, pipeline_run_id=execution_run_id)


def assert_all_nodes_terminal(graph_spec: GraphSpec) -> None:
    """Assert that no nodes are left in RUNNING or SCHEDULED state."""
    terminal_statuses = {NodeStatus.SUCCEEDED, NodeStatus.FAILED, NodeStatus.CANCELED, NodeStatus.SKIPPED}
    for node in graph_spec.nodes:
        assert node.status in terminal_statuses, f"Node '{node.node_id}' (pipe_code={node.pipe_code}) has non-terminal status: {node.status}"


def edges_by_kind(graph_spec: GraphSpec) -> dict[EdgeKind, list[EdgeSpec]]:
    """Group edges by their EdgeKind for targeted assertions."""
    result: dict[EdgeKind, list[EdgeSpec]] = defaultdict(list)
    for edge in graph_spec.edges:
        result[edge.kind].append(edge)
    return dict(result)


def ndjson_files_for_run(traces_dir: str, pipeline_run_id: str) -> list[Path]:
    """List all NDJSON files generated for a pipeline run."""
    run_dir = Path(traces_dir) / pipeline_run_id
    if not run_dir.exists():
        return []
    return sorted(run_dir.glob("*.ndjson"))


def node_pipe_codes(graph_spec: GraphSpec) -> set[str | None]:
    """Extract the set of pipe_codes from all nodes in a GraphSpec."""
    return {node.pipe_code for node in graph_spec.nodes}


_RUNNER_FAKE_INFERENCE_MODEL_NAME = "split_runner_fake"
_RUNNER_FAKE_INFERENCE_MODEL_ID = "split_runner_fake_id"
_RUNNER_FAKE_RESPONSE_TEXT = "split-worker fake response"


@activity.defn(name="act_llm_gen_text")
async def _runner_isolated_act_llm_gen_text(llm_assignment: LLMAssignment) -> str:  # noqa: RUF029
    """Substitute for `act_llm_gen_text` that exercises the Phase-2 runner-side fallback.

    Within a single pytest process the router worker registers a context via
    `set_event_log` on the process-wide `ReportingManager` singleton; a real
    runner activity in the same process would otherwise hit that same dict and
    take the fast path, masking the cross-worker bug. Instead this activity:

    - Clears `_event_log_contexts` on entry, simulating a cold runner process.
    - Synthesizes an `LLMJob` with non-zero usage and reports it via
      `report_inference_job`. The reporting path runs synchronously in the
      activity, so `_emit_usage_event` sees the cleared contexts dict and
      takes the fallback (writes to the per-process activity event log).
    - Returns a fixed string so the calling workflow can finish without
      attempting a real LLM call.

    This avoids the LIVE/DRY-mode dilemma: the existing `pipe_job_from_bundle`
    fixture defaults to DRY mode, where the LLM activity is normally bypassed
    by `ContentGeneratorDry` reporting inline inside the workflow. Subbing
    `act_llm_gen_text` with this version forces the activity to fire from the
    workflow's `start_activity` call (because we route `act_llm_gen_text` to
    `q_runner` via `worker_config.activity_queues`), exercising the
    cross-worker path even in DRY mode and keeping the test hermetic.
    """
    delegate = get_report_delegate()
    if isinstance(delegate, ReportingManager):
        delegate._event_log_contexts.clear()  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

    now = datetime.now()
    synthetic_metadata = llm_assignment.job_metadata.model_copy(
        update={
            "started_at": llm_assignment.job_metadata.started_at or now,
            "completed_at": now,
        },
    )
    tokens_usage = LLMTokensUsage(
        job_metadata=synthetic_metadata,
        inference_model_name=_RUNNER_FAKE_INFERENCE_MODEL_NAME,
        inference_model_id=_RUNNER_FAKE_INFERENCE_MODEL_ID,
        unit_costs={CostCategory.INPUT: 0.0, CostCategory.OUTPUT: 0.0},
        nb_tokens_by_category={TokenCategory.INPUT: 1, TokenCategory.OUTPUT: 1},
    )
    synthetic_job = LLMJob(
        job_metadata=synthetic_metadata,
        llm_prompt=llm_assignment.llm_prompt,
        job_params=llm_assignment.llm_setting.make_llm_job_params(),
        job_config=LLMJobConfig(schema_reask_max_attempts=1),
        job_report=LLMJobReport(llm_tokens_usage=tokens_usage),
    )
    delegate.report_inference_job(inference_job=synthetic_job)
    return _RUNNER_FAKE_RESPONSE_TEXT


@asynccontextmanager
async def make_split_workers(
    temporal_client: TemporalClient,
    q_router: str,
    q_runner: str,
) -> AsyncGenerator[None, None]:
    """Open two scoped workers on two task queues in the current process.

    - `q_router`: workflows + `act_flush_trace_events`. We don't use the bare
      `router` scope (`disable_all_activities=True`) here because
      `WfPipeRouter.run` dispatches `act_flush_trace_events` without a
      `task_queue` argument — the activity lands on the workflow's own queue
      and would never be picked up if the router registered no activities.
    - `q_runner`: activity-only (runner scope, `disable_all_workflows=True`),
      with `act_llm_gen_text` substituted by the isolation wrapper that clears
      the in-process `_event_log_contexts` cache so the runner cannot
      accidentally use the router's registered context.

    Pair this with `worker_config.activity_queues[act_llm_gen_text.__name__] =
    ActivityRouteConfig(default=q_runner, by_handle={})` so the workflow on
    `q_router` actually dispatches `act_llm_gen_text` to `q_runner`.
    """
    worker_scopes = get_config().temporal.worker_scopes
    base_router = worker_scopes.scopes["router"]
    runner_scope = worker_scopes.scopes["runner"]

    # Override the bare router scope to also register `act_flush_trace_events`
    # so the workflow's flush call does not deadlock waiting for an activity
    # worker on q_router. We keep `disable_all_activities=True` and add the
    # activity back via `required_activities` — but resolution clears
    # `disable_all_activities` last, so we instead use an empty exclude set
    # against the runner scope's activity surface.
    router_scope = base_router.model_copy(
        update={
            "disable_all_activities": False,
            "required_activities": ["act_flush_trace_events"],
            "excluded_activities": [
                "act_llm_gen_text",
                "act_llm_gen_object",
                "act_llm_gen_object_list",
                "act_img_gen_images",
                "act_jinja2_gen_text",
                "act_extract_gen_extract_pages",
                "act_render_page_views",
                "act_assemble_tracing",
                "act_deliver",
            ],
        },
    )

    async with (
        get_task_manager().make_worker(
            temporal_client,
            task_queue=q_router,
            is_not_sandboxed=True,
            scope=router_scope,
        ),
        get_task_manager().make_worker(
            temporal_client,
            task_queue=q_runner,
            is_not_sandboxed=True,
            scope=runner_scope,
            substitute_activities={act_llm_gen_text: _runner_isolated_act_llm_gen_text},
        ),
    ):
        yield
