"""Pipeline-level dry run with graph generation.

Provides a single entrypoint to dry-run an entire pipeline from MTHDS content,
producing a GraphSpec. Used by both the CLI graph commands and the API.
"""

from pipelex.base_exceptions import PipelexError
from pipelex.config import get_config
from pipelex.core.interpreter.exceptions import PipelexInterpreterError
from pipelex.core.interpreter.interpreter import PipelexInterpreter
from pipelex.graph.graphspec import GraphSpec
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipeline.runner import PipelexRunner


async def dry_run_pipeline(
    mthds_content: str,
    bundle_uri: str | None = None,
    library_dirs: list[str] | None = None,
) -> tuple[GraphSpec, str]:
    """Dry-run a full pipeline from MTHDS content, producing a GraphSpec.

    Parses the content, identifies the main pipe, and executes the pipeline
    in dry-run mode with graph tracing enabled and mock inputs.

    Args:
        mthds_content: MTHDS bundle content as a string.
        bundle_uri: Optional URI for the bundle (used by runner for context).
        library_dirs: Optional library directories for pipe resolution.

    Returns:
        Tuple of (GraphSpec, pipe_code).

    Raises:
        PipelexInterpreterError: If content parsing fails or main_pipe is missing.
        PipelexError: If pipeline execution does not produce a graph spec.
        PipelineExecutionError: If dry-run execution fails.
    """
    bundle_blueprint = PipelexInterpreter.make_pipelex_bundle_blueprint(mthds_content=mthds_content)
    main_pipe_code = bundle_blueprint.main_pipe
    if not main_pipe_code:
        msg = "Bundle does not declare a main_pipe, cannot generate graph"
        raise PipelexInterpreterError(msg)
    pipe_code: str = main_pipe_code

    execution_config = get_config().pipelex.pipeline_execution_config.with_graph_config_overrides(
        generate_graph=True,
        mock_inputs=True,
    )

    runner = PipelexRunner(
        bundle_uri=bundle_uri,
        pipe_run_mode=PipeRunMode.DRY,
        execution_config=execution_config,
        library_dirs=library_dirs or [],
    )
    response = await runner.execute_pipeline(
        pipe_code=pipe_code,
        mthds_content=mthds_content,
    )
    pipe_output = response.pipe_output

    if not pipe_output.graph_spec:
        msg = "Pipeline execution did not produce a graph spec"
        raise PipelexError(msg)

    return pipe_output.graph_spec, pipe_code
