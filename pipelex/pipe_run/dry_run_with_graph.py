from pipelex.config import get_config
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.pipes.pipe_abstract import PipeAbstract
from pipelex.graph.graph_config import DataInclusionConfig
from pipelex.graph.graph_tracer_manager import GraphTracerManager
from pipelex.graph.graphspec import GraphSpec
from pipelex.pipe_run.dry_run import convert_to_working_memory_format
from pipelex.pipe_run.pipe_run_params import PipeRunMode
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.pipeline.job_metadata import JobMetadata
from pipelex.pipeline.pipeline_models import SpecialPipelineId
from pipelex.system.telemetry.otel_constants import OTelConstants


async def dry_run_pipe_with_graph(
    pipe: PipeAbstract,
    graph_id: str | None = None,
    data_inclusion: DataInclusionConfig | None = None,
) -> GraphSpec:
    """Dry run a pipe while capturing its execution graph.

    Args:
        pipe: The pipe to dry run.
        graph_id: Optional graph ID. If not provided, uses the pipe code.
        data_inclusion: Optional configuration controlling which data formats to capture.
            If not provided, uses the default from the pipelex config.

    Returns:
        GraphSpec containing the execution graph of the dry run.

    Raises:
        Various exceptions if the dry run fails.
    """
    # Get or create the graph tracer manager singleton
    manager = GraphTracerManager.get_or_create_instance()
    effective_graph_id = graph_id or f"dry_run_{pipe.code}"
    effective_data_inclusion = data_inclusion or get_config().pipelex.pipeline_execution_config.graph_config.data_inclusion

    try:
        graph_context = manager.open_tracer(
            graph_id=effective_graph_id,
            data_inclusion=effective_data_inclusion,
            pipeline_ref_domain=pipe.domain_code,
            pipeline_ref_main_pipe=pipe.code,
        )

        # Get needed inputs and create working memory
        needed_inputs_for_factory = convert_to_working_memory_format(needed_inputs_spec=pipe.needed_inputs())
        working_memory = WorkingMemoryFactory.make_mock_inputs(needed_inputs=needed_inputs_for_factory)

        # Validate the pipe
        pipe.validate_with_libraries()

        # Create job metadata with graph context - the tracing will be done in run_pipe
        job_metadata = JobMetadata(
            user_id=OTelConstants.DEFAULT_USER_ID,
            pipeline_run_id=SpecialPipelineId.DRY_RUN_UNTITLED,
            graph_context=graph_context,
        )

        # Run the pipe in dry mode - run_pipe will handle the graph tracing
        await pipe.run_pipe(
            job_metadata=job_metadata,
            working_memory=working_memory,
            pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=PipeRunMode.DRY),
        )

        # Finalize and return the graph
        result = manager.close_tracer(effective_graph_id)
        if result is None:
            # This shouldn't happen if open_tracer was called, but handle it gracefully
            msg = "GraphTracer close_tracer returned None unexpectedly"
            raise RuntimeError(msg)

        return result

    except Exception:
        # Clean up the tracer on error
        manager.close_tracer(effective_graph_id)
        raise
