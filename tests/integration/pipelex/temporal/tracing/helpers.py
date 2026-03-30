"""Shared test helpers for Temporal graph tracing integration tests."""

import uuid
from collections import defaultdict
from pathlib import Path

from temporalio.client import Client as TemporalClient

from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.graph.graph_config import DataInclusionConfig
from pipelex.graph.graph_context import GraphContext
from pipelex.graph.graphspec import EdgeKind, EdgeSpec, GraphSpec, NodeStatus, PipelineRef
from pipelex.pipe_run.pipe_job import PipeJob
from pipelex.temporal.temporal_hub import get_task_manager
from pipelex.temporal.tprl_pipe.wf_pipe_router import WfPipeRouter
from pipelex.tracing.graphspec_assembler import GraphSpecAssembler
from pipelex.tracing.ndjson_event_log import NdjsonEventLog
from tests.integration.pipelex.temporal.library_crate.helpers import rehydrate_pipe_output


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
