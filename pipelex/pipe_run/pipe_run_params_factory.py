from typing import Any

from pipelex.config import get_config
from pipelex.core.pipes.variable_multiplicity import VariableMultiplicity
from pipelex.pipe_run.pipe_run_params import BatchParams, PipeRunMode, PipeRunParams


class PipeRunParamsFactory:
    @classmethod
    def make_run_params(
        cls,
        pipe_run_mode: PipeRunMode = PipeRunMode.LIVE,
        pipe_stack_limit: int | None = None,
        output_multiplicity: VariableMultiplicity | None = None,
        dynamic_output_concept_code: str | None = None,
        batch_params: BatchParams | None = None,
        params: dict[str, Any] | None = None,
    ) -> PipeRunParams:
        pipe_stack_limit = pipe_stack_limit or get_config().pipelex.pipe_run_config.pipe_stack_limit
        return PipeRunParams(
            run_mode=pipe_run_mode,
            pipe_stack_limit=pipe_stack_limit,
            output_multiplicity=output_multiplicity,
            dynamic_output_concept_code=dynamic_output_concept_code,
            batch_params=batch_params,
            params=params or {},
        )
