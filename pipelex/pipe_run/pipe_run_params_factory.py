from typing import Any

from pipelex import log
from pipelex.cogt.content_generation.cogt_run_params import check_mock_usage_requires_dry
from pipelex.config import get_config
from pipelex.core.pipes.variable_multiplicity import VariableMultiplicity
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipe_run.pipe_run_params import BatchParams, PipeRunParams
from pipelex.runtime_hub import is_dry_run_forced


class PipeRunParamsFactory:
    @classmethod
    def make_run_params(
        cls,
        *,
        pipe_run_mode: PipeRunMode = PipeRunMode.LIVE,
        is_mock_usage: bool = False,
        pipe_stack_limit: int | None = None,
        output_multiplicity: VariableMultiplicity | None = None,
        dynamic_output_concept_ref: str | None = None,
        batch_params: BatchParams | None = None,
        params: dict[str, Any] | None = None,
    ) -> PipeRunParams:
        """Single writer of ``run_mode`` and ``is_mock_usage`` — direct fields on ``PipeRunParams``.

        The keyless-boot forced-DRY flag (eng review D4) is resolved HERE — at the single writer —
        so every execution entry point is covered (``prepare_pipe_job``, the runtime bridge,
        ``PipeJobFactory`` defaults), not just the pipeline-API path.

        The REQUESTED mode is validated before the forced-DRY coercion, so a contract violation
        (``is_mock_usage`` on a LIVE request) fails loud on every boot — the keyless coercion must
        not silently turn an illegal request into a legal one.
        """
        check_mock_usage_requires_dry(run_mode=pipe_run_mode, is_mock_usage=is_mock_usage)
        if is_dry_run_forced() and pipe_run_mode.is_live:
            log.warning(
                "LIVE run requested under a keyless boot (needs_inference=False): forcing run_mode to DRY — "
                "outputs will be synthetic mocks, not real inference."
            )
            pipe_run_mode = PipeRunMode.DRY
        pipe_stack_limit = pipe_stack_limit or get_config().pipelex.pipe_run_config.pipe_stack_limit
        return PipeRunParams(
            run_mode=pipe_run_mode,
            is_mock_usage=is_mock_usage,
            pipe_stack_limit=pipe_stack_limit,
            output_multiplicity=output_multiplicity,
            dynamic_output_concept_ref=dynamic_output_concept_ref,
            batch_params=batch_params,
            params=params or {},
        )
