"""Cogt-tier slice of the run params (D-plan Part B).

``CogtRunParams`` carries the execution-mode contract down to the cogt leaf. The
facts (``run_mode``, ``is_mock_usage``) are owned by ``PipeRunParams`` as direct
fields; its derived ``cogt_run_params`` property mints this carrier on demand, so
there is exactly one stored copy. Single writer of the facts:
``PipeRunParamsFactory.make_run_params`` (fed by ``prepare_pipe_job``).

Route to the leaf: operators slice ``pipe_run_params.cogt_run_params`` off and pass
it into the content-generator protocol methods; generators stamp it as a field on
every cogt assignment (``LLMAssignment``, ``ImgGenAssignment``, ...), which
serializes whole across the Temporal activity boundary — so the leaf sees the same
``run_mode`` whether it runs inline or inside an ``act_*_gen_*`` activity. That is
what makes ``run_mode`` orthogonal to the backend (D-plan §3.5).

Deliberately NOT ``PipeRunParams`` itself: threading the pipe-tier params into cogt
would drag pipe-only concepts (multiplicity, batch params, pipe stack) into a layer
that must stay pipe-agnostic. This class is the cogt slice and grows only
cogt-relevant flags.
"""

from typing import Self

from pydantic import BaseModel, ConfigDict, model_validator

from pipelex.pipe_run.pipe_run_mode import PipeRunMode


def check_mock_usage_requires_dry(*, run_mode: PipeRunMode, is_mock_usage: bool) -> None:
    """Single home of the rule: ``is_mock_usage`` is a sub-flag of ``run_mode=DRY``.

    Raises ``ValueError`` on the illegal LIVE combination — called by the model validators on
    both ``CogtRunParams`` and ``PipeRunParams`` (each guards its own boundary) and by
    ``PipeRunParamsFactory.make_run_params`` (which must reject the REQUESTED mode before the
    keyless forced-DRY coercion can mask it).
    """
    if is_mock_usage and run_mode.is_live:
        msg = "is_mock_usage is a sub-flag of run_mode=DRY: it cannot be set on a LIVE run"
        raise ValueError(msg)


class CogtRunParams(BaseModel):
    """Execution-mode contract carried on every cogt assignment (crosses the Temporal wire).

    There is exactly one non-live mode: ``run_mode=DRY`` (no provider calls, no storage IO, no
    user-code execution). ``is_mock_usage`` is a secondary, internal flag that only has meaning
    on a DRY run — setting it on a LIVE carrier is a contract violation rejected at validation.
    """

    # `extra="forbid"`: a stale or typo'd key on a wire payload must fail loud (mirrors
    # PipeRunParams). `frozen=True`: the carrier is an immutable value object — once minted from
    # `PipeRunParams.cogt_run_params` and stamped on an assignment, no leaf can mutate the
    # execution contract mid-run. `run_mode` is REQUIRED: a wire payload that omits it must fail
    # loud rather than silently default to the spending direction (LIVE) or the mock direction
    # (DRY).
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_mode: PipeRunMode

    # Internal sub-flag of DRY — only CLI access is the hidden `--mock-usage` test trigger
    # (requires `--dry-run`, not shown in --help): when True, the dry LLM leaves report
    # *non-zero* synthetic usage (deterministic sentinel counts, $0 cost) so the end-of-run cost
    # report renders — the cheap, deterministic cross-worker cost-report validation affordance.
    # Default False keeps dry runs zero-token with the report suppressed. Single writer:
    # ``PipeRunParamsFactory.make_run_params`` (fed by ``prepare_pipe_job``).
    is_mock_usage: bool = False

    @model_validator(mode="after")
    def validate_mock_usage_requires_dry(self) -> Self:
        check_mock_usage_requires_dry(run_mode=self.run_mode, is_mock_usage=self.is_mock_usage)
        return self
