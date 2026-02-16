from __future__ import annotations

from typing import TYPE_CHECKING

from pipelex.pipeline.runner import PipelexRunner

if TYPE_CHECKING:
    from mthds.models.pipe_output import VariableMultiplicity
    from mthds.models.pipeline_inputs import PipelineInputs

    from pipelex.core.memory.working_memory import WorkingMemory
    from pipelex.core.pipes.pipe_output import PipeOutput
    from pipelex.pipe_run.pipe_run_mode import PipeRunMode
    from pipelex.system.configuration.configs import PipelineExecutionConfig


async def execute_pipeline(
    user_id: str | None = None,
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
    execution_config: PipelineExecutionConfig | None = None,
) -> PipeOutput:
    """Execute a pipeline and wait for its completion.

    Convenience wrapper around PipelexRunner that preserves the legacy function signature.
    """
    runner = PipelexRunner(
        library_id=library_id,
        library_dirs=library_dirs,
        bundle_uri=bundle_uri,
        pipe_run_mode=pipe_run_mode,
        search_domain_codes=search_domain_codes,
        user_id=user_id,
        execution_config=execution_config,
    )
    response = await runner.execute_pipeline(
        pipe_code=pipe_code,
        mthds_content=plx_content,
        inputs=inputs,
        output_name=output_name,
        output_multiplicity=output_multiplicity,
        dynamic_output_concept_code=dynamic_output_concept_code,
    )
    return response.pipe_output
