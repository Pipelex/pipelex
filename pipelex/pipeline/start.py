import asyncio
from pathlib import Path
from typing import TYPE_CHECKING

from pipelex.client.protocol import PipelineInputs
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.hub import (
    get_library_manager,
    get_pipe_router,
    get_pipeline_manager,
    get_report_delegate,
    get_required_pipe,
    get_telemetry_manager,
    set_current_library_id,
)
from pipelex.pipe_run.pipe_job_factory import PipeJobFactory
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipe_run.pipe_run_params import (
    FORCE_DRY_RUN_MODE_ENV_KEY,
    VariableMultiplicity,
)
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.pipeline.exceptions import PipeExecutionError
from pipelex.pipeline.job_metadata import JobMetadata
from pipelex.pipeline.validate_bundle import validate_bundle
from pipelex.system.environment import get_optional_env
from pipelex.system.telemetry.events import EventName, EventProperty

if TYPE_CHECKING:
    from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint
    from pipelex.core.pipes.pipe_abstract import PipeAbstract


async def start_pipeline(
    library_id: str | None = None,
    library_path: str | None = None,
    pipe_code: str | None = None,
    plx_content: str | None = None,
    inputs: PipelineInputs | WorkingMemory | None = None,
    output_name: str | None = None,
    output_multiplicity: VariableMultiplicity | None = None,
    dynamic_output_concept_code: str | None = None,
    pipe_run_mode: PipeRunMode | None = None,
    search_domains: list[str] | None = None,
) -> tuple[str, asyncio.Task[PipeOutput]]:
    """Start a pipeline in the background.

    This function mirrors *execute_pipeline* but returns immediately with the
    ``pipeline_run_id`` and a task instead of waiting for the pipe run to complete.
    The actual execution is scheduled on the current event-loop using
    :pyfunc:`asyncio.create_task`.

    Parameters
    ----------
    library_id:
        The library ID to use for the pipeline execution. If not provided, the current library ID is used.
    library_path:
        Path to the library directory to load.
    pipe_code:
        The code identifying the pipeline to execute.
    plx_content:
        Content of the pipeline bundle to execute.
    inputs:
        Inputs passed to the pipeline.
    output_name:
        Name of the output slot to write to.
    output_multiplicity:
        Output multiplicity.
    dynamic_output_concept_code:
        Override the dynamic output concept code.
    pipe_run_mode:
        Pipe run mode: if specified, it must be ``PipeRunMode.LIVE`` or ``PipeRunMode.DRY``.
        If not specified, the pipe run mode is inferred from the environment variable
        ``PIPELEX_FORCE_DRY_RUN_MODE``. If the environment variable is not set,
        the pipe run mode is ``PipeRunMode.LIVE``.
    search_domains:
        List of domains to search for pipes.

    Returns:
    -------
    Tuple[str, asyncio.Task[PipeOutput]]
        The ``pipeline_run_id`` of the newly started pipeline and a task that
        can be awaited to get the pipe output.

    """
    if not plx_content and not pipe_code:
        msg = "Either pipe_code or plx_content must be provided to the API start_pipeline."
        raise ValueError(msg)

    pipeline = get_pipeline_manager().add_new_pipeline()
    pipeline_run_id = pipeline.pipeline_run_id

    if not library_id:
        library_id = pipeline_run_id

    library_manager = get_library_manager()
    set_current_library_id(library_id=library_id)
    library_manager.open_library(library_id=library_id)

    pipe: PipeAbstract | None = None
    blueprint: PipelexBundleBlueprint | None = None

    if plx_content:
        validate_bundle_result = await validate_bundle(plx_content=plx_content)
        library_manager.load_from_blueprints(library_id=library_id, blueprints=validate_bundle_result.blueprints)
        # For now, we only support one blueprint when given a plx_content. So blueprints is of length 1.
        blueprint = validate_bundle_result.blueprints[0]
        if pipe_code:
            pipe = get_required_pipe(pipe_code=pipe_code)
        elif blueprint.main_pipe:
            pipe = get_required_pipe(pipe_code=blueprint.main_pipe)
        else:
            msg = "No pipe code or main pipe in the PLX content provided to the API start_pipeline."
            raise PipeExecutionError(message=msg)
    elif pipe_code:
        if library_path:
            library_manager.load_libraries(library_id=library_id, library_dirs=[Path(library_path)])
        else:
            library_manager.load_libraries(library_id=library_id)
        pipe = get_required_pipe(pipe_code=pipe_code)
    else:
        msg = "Either provide pipe_code or plx_content to the API start_pipeline. 'pipe_code' must be provided when 'plx_content' is None"
        raise PipeExecutionError(message=msg)

    search_domains = search_domains or []
    if pipe.domain not in search_domains:
        search_domains.insert(0, pipe.domain)

    working_memory: WorkingMemory | None = None

    if inputs:
        if isinstance(inputs, WorkingMemory):
            working_memory = inputs
        else:
            working_memory = WorkingMemoryFactory.make_from_pipeline_inputs(
                pipeline_inputs=inputs,
                search_domains=search_domains,
            )

    if pipe_run_mode is None:
        if run_mode_from_env := get_optional_env(key=FORCE_DRY_RUN_MODE_ENV_KEY):
            pipe_run_mode = PipeRunMode(run_mode_from_env)
        else:
            pipe_run_mode = PipeRunMode.LIVE

    get_report_delegate().open_registry(pipeline_run_id=pipeline_run_id)

    job_metadata = JobMetadata(
        pipeline_run_id=pipeline.pipeline_run_id,
    )

    pipe_run_params = PipeRunParamsFactory.make_run_params(
        output_multiplicity=output_multiplicity,
        dynamic_output_concept_code=dynamic_output_concept_code,
        pipe_run_mode=pipe_run_mode,
    )

    pipe_job = PipeJobFactory.make_pipe_job(
        pipe=pipe,
        pipe_run_params=pipe_run_params,
        job_metadata=job_metadata,
        working_memory=working_memory,
        output_name=output_name,
    )

    properties = {
        EventProperty.PIPELINE_RUN_ID: job_metadata.pipeline_run_id,
        EventProperty.PIPE_TYPE: pipe.pipe_type,
    }
    get_telemetry_manager().track_event(event_name=EventName.PIPELINE_EXECUTE, properties=properties)

    # Launch execution without awaiting the result.
    task: asyncio.Task[PipeOutput] = asyncio.create_task(get_pipe_router().run(pipe_job))

    return pipeline.pipeline_run_id, task
