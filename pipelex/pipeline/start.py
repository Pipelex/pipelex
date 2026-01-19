import asyncio
from pathlib import Path

from pipelex.client.protocol import PipelineInputs
from pipelex.config import get_config
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.hub import get_pipe_router
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipe_run.pipe_run_params import VariableMultiplicity
from pipelex.pipeline.pipeline_run_setup import pipeline_run_setup
from pipelex.system.configuration.configs import PipelineExecutionConfig


async def start_pipeline(
    library_id: str | None = None,
    library_dirs: list[str] | None = None,
    pipe_code: str | None = None,
    plx_content: str | None = None,
    bundle_uri: str | None = None,
    inputs: PipelineInputs | WorkingMemory | None = None,
    output_name: str | None = None,
    output_multiplicity: VariableMultiplicity | None = None,
    dynamic_output_concept_code: str | None = None,
    pipe_run_mode: PipeRunMode | None = None,
    search_domain_codes: list[str] | None = None,
    user_id: str | None = None,
    execution_config: PipelineExecutionConfig | None = None,
) -> tuple[str, asyncio.Task[PipeOutput]]:
    """Start a pipeline in the background.

    This function mirrors ``execute_pipeline`` but returns immediately with the
    ``pipeline_run_id`` and a task instead of waiting for the pipe run to complete.
    The actual execution is scheduled on the current event loop using
    ``asyncio.create_task``.

    Parameters
    ----------
    library_id:
        Unique identifier for the library instance. If not provided, defaults to the
        auto-generated ``pipeline_run_id``. Use a custom ID when you need to manage
        multiple library instances or maintain library state across executions.
    library_dirs:
        List of directory paths to load pipe definitions from. Combined with directories
        from the ``PIPELEXPATH`` environment variable (PIPELEXPATH directories are searched
        first). When provided alongside ``plx_content``, definitions from both sources
        are loaded into the library.
    pipe_code:
        Code identifying the pipe to execute. Required when ``plx_content`` is not
        provided. When both ``plx_content`` and ``pipe_code`` are provided, the
        specified pipe from the PLX content will be executed (overriding any
        ``main_pipe`` defined in the content).
    plx_content:
        Complete PLX file content as a string. The pipe to execute is determined by
        ``pipe_code`` (if provided) or the ``main_pipe`` property in the PLX content.
        Can be combined with ``library_dirs`` to load additional definitions.
    bundle_uri:
        URI identifying the bundle. If ``plx_content`` is not provided and ``bundle_uri``
        points to a local file path, the content will be read from that file. Also used
        to detect if the bundle was already loaded from library directories (e.g., via
        PIPELEXPATH) to avoid duplicate domain registration.
    inputs:
        Inputs passed to the pipeline. Can be either a ``PipelineInputs`` dictionary
        or a ``WorkingMemory`` instance.
    output_name:
        Name of the output slot to write to.
    output_multiplicity:
        Output multiplicity specification.
    dynamic_output_concept_code:
        Override the dynamic output concept code.
    pipe_run_mode:
        Pipe run mode: ``PipeRunMode.LIVE`` or ``PipeRunMode.DRY``. If not specified,
        inferred from the environment variable ``PIPELEX_FORCE_DRY_RUN_MODE``. Defaults
        to ``PipeRunMode.LIVE`` if the environment variable is not set.
    search_domain_codes:
        List of domain codes to search for pipes. The executed pipe's domain is automatically
        added if not already present.
    user_id:
        Unique identifier for the user.
    execution_config:
        Pipeline execution configuration including graph tracing settings.
        If not provided, uses the default from
        ``get_config().pipelex.pipeline_execution_config``. Use the ``mock_inputs``
        field to generate mock data for missing required inputs during dry-run.
        Since this function returns immediately, the caller is responsible for calling
        ``GraphTracerManager.get_instance().close_tracer(pipeline_run_id)``
        after the task completes to retrieve the GraphSpec.

    Returns:
    -------
    tuple[str, asyncio.Task[PipeOutput]]
        The ``pipeline_run_id`` of the newly started pipeline and a task that
        can be awaited to get the pipe output.

    """
    # Use provided config or get default
    execution_config = execution_config or get_config().pipelex.pipeline_execution_config

    # If plx_content is not provided but bundle_uri points to a file, read it
    if plx_content is None and bundle_uri is not None:
        bundle_path = Path(bundle_uri)
        if bundle_path.is_file():
            plx_content = bundle_path.read_text(encoding="utf-8")

    # TODO: make sure we close the graph tracer after the task completes
    pipe_job, pipeline_run_id, _library_id = await pipeline_run_setup(
        execution_config=execution_config,
        library_id=library_id,
        library_dirs=library_dirs,
        pipe_code=pipe_code,
        plx_content=plx_content,
        bundle_uri=bundle_uri,
        inputs=inputs,
        output_name=output_name,
        output_multiplicity=output_multiplicity,
        dynamic_output_concept_code=dynamic_output_concept_code,
        pipe_run_mode=pipe_run_mode,
        search_domain_codes=search_domain_codes,
        user_id=user_id,
    )

    task: asyncio.Task[PipeOutput] = asyncio.create_task(get_pipe_router().run(pipe_job))

    return pipeline_run_id, task
