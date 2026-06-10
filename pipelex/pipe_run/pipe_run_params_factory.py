from typing import Any

from pipelex import log
from pipelex.cogt.content_generation.cogt_run_params import CogtRunParams
from pipelex.config import get_config
from pipelex.core.pipes.variable_multiplicity import VariableMultiplicity
from pipelex.hub import is_dry_run_forced
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipe_run.pipe_run_params import BatchParams, PipeRunParams


class PipeRunParamsFactory:
    @classmethod
    def make_run_params(
        cls,
        pipe_run_mode: PipeRunMode = PipeRunMode.LIVE,
        is_mock_inference: bool = False,
        pipe_stack_limit: int | None = None,
        output_multiplicity: VariableMultiplicity | None = None,
        dynamic_output_concept_ref: str | None = None,
        batch_params: BatchParams | None = None,
        params: dict[str, Any] | None = None,
    ) -> PipeRunParams:
        """Single writer of ``run_mode`` and ``is_mock_inference``: builds the nested ``CogtRunParams`` here (D2/D8).

        The keyless-boot forced-DRY flag (eng review D4) is resolved HERE — at the single writer —
        so every execution entry point is covered (``prepare_pipe_job``, the runtime bridge,
        ``PipeJobFactory`` defaults), not just the pipeline-API path.
        """
        if is_dry_run_forced():
            if pipe_run_mode.is_live and is_mock_inference:
                log.warning(
                    "--mock-inference requested under a keyless boot (needs_inference=False): the run is forced "
                    "to DRY, which takes precedence at the leaf — the rendered synthetic cost report will NOT be "
                    "produced (DRY usage is zero-token and suppressed). Boot with inference configured to use "
                    "--mock-inference."
                )
            pipe_run_mode = PipeRunMode.DRY
        pipe_stack_limit = pipe_stack_limit or get_config().pipelex.pipe_run_config.pipe_stack_limit
        return PipeRunParams(
            cogt_run_params=CogtRunParams(run_mode=pipe_run_mode, is_mock_inference=is_mock_inference),
            pipe_stack_limit=pipe_stack_limit,
            output_multiplicity=output_multiplicity,
            dynamic_output_concept_ref=dynamic_output_concept_ref,
            batch_params=batch_params,
            params=params or {},
        )
