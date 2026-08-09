from typing import Any

from pipelex.cogt.content_generation.cogt_run_params import check_mock_usage_requires_dry
from pipelex.config import get_config
from pipelex.core.pipes.variable_multiplicity import VariableMultiplicity
from pipelex.pipe_run.pipe_run_params import BatchParams, PipeRunParams
from pipelex.runtime_hub import resolve_run_mode_for_boot
from pipelex.system.pipe_run_mode import PipeRunMode


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

        The keyless-boot forced-DRY flag (eng review D4) is applied HERE — at the single writer of
        those fields — so every pipe-tier execution entry point is covered (``prepare_pipe_job``,
        the runtime bridge, ``PipeJobFactory`` defaults), not just the pipeline-API path. The rule
        itself lives in ``resolve_run_mode_for_boot`` rather than inline, because the kernel tier's
        ``PipelexKernel.make`` mints its own ``CogtRunParams`` and must apply the identical rule.

        The REQUESTED mode is validated before the forced-DRY coercion, so a contract violation
        (``is_mock_usage`` on a LIVE request) fails loud on every boot — the keyless coercion must
        not silently turn an illegal request into a legal one.
        """
        check_mock_usage_requires_dry(run_mode=pipe_run_mode, is_mock_usage=is_mock_usage)
        pipe_run_mode = resolve_run_mode_for_boot(requested=pipe_run_mode)
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
