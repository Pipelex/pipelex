from typing import Any, Dict, Optional

from pipelex.config import get_config
from pipelex.core.pipes.pipe_run_params import BatchParams, PipeOutputMultiplicity, PipeRunMode, PipeRunParams


class PipeRunParamsFactory:
    @classmethod
    def make_run_params(
        cls,
        pipe_run_mode: PipeRunMode = PipeRunMode.LIVE,
        pipe_stack_limit: Optional[int] = None,
        output_multiplicity: Optional[PipeOutputMultiplicity] = None,
        dynamic_output_concept_code: Optional[str] = None,
        batch_params: Optional[BatchParams] = None,
        params: Optional[Dict[str, Any]] = None,
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
