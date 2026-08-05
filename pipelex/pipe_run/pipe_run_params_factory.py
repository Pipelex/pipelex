from typing import Any

from pipelex import log
from pipelex.cogt.content_generation.cogt_run_params import check_mock_usage_requires_dry
from pipelex.config import get_config
from pipelex.core.pipes.variable_multiplicity import VariableMultiplicity
from pipelex.pipe_run.pipe_run_params import BatchParams, PipeRunParams
from pipelex.runtime_hub import is_dry_run_forced
from pipelex.system.pipe_run_mode import PipeRunMode


def resolve_batch_max_concurrency(max_concurrency_setting: int | str) -> int | None:
    """Translate the ``pipeline_execution_config.max_concurrency`` setting into a ``gather_bounded`` bound.

    The config exposes the explicit literal ``"unbounded"``; ``gather_bounded`` takes ``None`` for no
    bound. Any int value is passed through unchanged. Centralizing this guards against passing the
    raw ``"unbounded"`` string into ``gather_bounded``, which would raise ``TypeError`` on its
    ``max_concurrency < 1`` check.

    Lives next to the factory because the factory is where the setting is read: the resolved bound is
    frozen into ``PipeRunParams.batch_max_concurrency`` at construction, never re-read at fan-out time.
    """
    return None if isinstance(max_concurrency_setting, str) else max_concurrency_setting


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
        """Single writer of ``run_mode``, ``is_mock_usage`` and ``batch_max_concurrency`` — direct fields on ``PipeRunParams``.

        The keyless-boot forced-DRY flag (eng review D4) is resolved HERE — at the single writer —
        so every execution entry point is covered (``prepare_pipe_job``, the runtime bridge,
        ``PipeJobFactory`` defaults), not just the pipeline-API path.

        The REQUESTED mode is validated before the forced-DRY coercion, so a contract violation
        (``is_mock_usage`` on a LIVE request) fails loud on every boot — the keyless coercion must
        not silently turn an illegal request into a legal one.

        ``batch_max_concurrency`` is resolved here for the same single-writer reason and because the
        read must happen ONCE, at submit time: see the field's docstring on ``PipeRunParams``.
        """
        check_mock_usage_requires_dry(run_mode=pipe_run_mode, is_mock_usage=is_mock_usage)
        if is_dry_run_forced() and pipe_run_mode.is_live:
            log.warning(
                "LIVE run requested under a keyless boot (needs_inference=False): forcing run_mode to DRY — "
                "outputs will be synthetic mocks, not real inference."
            )
            pipe_run_mode = PipeRunMode.DRY
        config = get_config().pipelex
        pipe_stack_limit = pipe_stack_limit or config.pipe_run_config.pipe_stack_limit
        return PipeRunParams(
            run_mode=pipe_run_mode,
            is_mock_usage=is_mock_usage,
            pipe_stack_limit=pipe_stack_limit,
            batch_max_concurrency=resolve_batch_max_concurrency(config.pipeline_execution_config.max_concurrency),
            output_multiplicity=output_multiplicity,
            dynamic_output_concept_ref=dynamic_output_concept_ref,
            batch_params=batch_params,
            params=params or {},
        )
