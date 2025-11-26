from pathlib import Path
from typing import TYPE_CHECKING

from pipelex.client.protocol import PipelineInputs
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.hub import (
    get_library_manager,
    get_pipeline_manager,
    get_report_delegate,
    get_required_pipe,
    get_telemetry_manager,
    set_current_library,
)
from pipelex.pipe_run.pipe_job import PipeJob
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


async def pipeline_run_setup(
    library_id: str | None = None,
    library_dirs: list[str] | None = None,
    pipe_code: str | None = None,
    plx_content: str | None = None,
    inputs: PipelineInputs | WorkingMemory | None = None,
    output_name: str | None = None,
    output_multiplicity: VariableMultiplicity | None = None,
    dynamic_output_concept_code: str | None = None,
    pipe_run_mode: PipeRunMode | None = None,
    search_domains: list[str] | None = None,
) -> tuple[PipeJob, str, str]:
    """Set up a pipeline for execution.

    This function handles all the common setup logic for both ``execute_pipeline``
    and ``start_pipeline``, including library setup, pipe loading, working memory
    initialization, and pipe job creation.

    Parameters
    ----------
    library_id:
        Unique identifier for the library instance. If not provided, defaults to the
        auto-generated ``pipeline_run_id``. Use a custom ID when you need to manage
        multiple library instances or maintain library state across executions.
    library_dirs:
        List of directory paths to load pipe definitions from. If not provided, loads
        from the current working directory (the directory from which the Python script
        is executed). Ignored when ``plx_content`` is provided.
    pipe_code:
        Code identifying the pipe to execute. Required when ``plx_content`` is not
        provided. When both ``plx_content`` and ``pipe_code`` are provided, the
        specified pipe from the PLX content will be executed (overriding any
        ``main_pipe`` defined in the content).
    plx_content:
        Complete PLX file content as a string. When provided, only this content is
        loaded into the library, creating an isolated execution environment. The pipe
        to execute is determined by ``pipe_code`` (if provided) or the ``main_pipe``
        property in the PLX content.
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
    search_domains:
        List of domains to search for pipes. The executed pipe's domain is automatically
        added if not already present.

    Returns:
    -------
    tuple[PipeJob, str, str]
        A tuple containing the pipe job ready for execution, the pipeline run ID,
        and the library ID.

    """
    if not plx_content and not pipe_code:
        msg = "Either pipe_code or plx_content must be provided to the pipeline API."
        raise ValueError(msg)

    pipeline = get_pipeline_manager().add_new_pipeline()
    pipeline_run_id = pipeline.pipeline_run_id

    if not library_id:
        library_id = pipeline_run_id

    library_manager = get_library_manager()
    set_current_library(library_id=library_id)
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
            msg = "No pipe code or main pipe in the PLX content provided to the pipeline API."
            raise PipeExecutionError(message=msg)
    elif pipe_code:
        if library_dirs:
            library_manager.load_libraries(library_id=library_id, library_dirs=[Path(library_dir) for library_dir in library_dirs])
        else:
            library_manager.load_libraries(library_id=library_id, library_dirs=[Path.cwd()])
        pipe = get_required_pipe(pipe_code=pipe_code)
    else:
        msg = "Either provide pipe_code or plx_content to the pipeline API. 'pipe_code' must be provided when 'plx_content' is None"
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

    return pipe_job, pipeline_run_id, library_id
