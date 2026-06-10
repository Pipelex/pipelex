"""Cogt-tier slice of the run params (D-plan Part B, eng review D2).

``CogtRunParams`` carries the execution-mode contract down to the cogt leaf. It is
the ONLY home of ``run_mode``: ``PipeRunParams`` nests an instance and exposes a
delegating ``run_mode`` property, so pipe-tier readers see one value with zero
duplication. Single writer: ``PipeRunParamsFactory.make_run_params`` (fed by
``prepare_pipe_job``).

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

from pydantic import BaseModel, ConfigDict

from pipelex.pipe_run.pipe_run_mode import PipeRunMode


class CogtRunParams(BaseModel):
    """Execution-mode contract carried on every cogt assignment (crosses the Temporal wire).

    Precedence at the leaf: ``run_mode=DRY`` wins over ``is_mock_inference`` — every leaf checks
    ``run_mode.is_dry`` first, so a DRY run with the mock flag set mocks dry (zero-token,
    suppressed report), never the reportable mock.
    """

    # `extra="forbid"`: a stale or typo'd key on a wire payload must fail loud (mirrors
    # PipeRunParams). `frozen=True`: the same carrier instance is shared by reference across every
    # assignment of a run — single-writer is enforced, not just convention. `run_mode` is REQUIRED:
    # a wire payload that omits it must fail loud rather than silently default to the spending
    # direction (LIVE) or the mock direction (DRY).
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_mode: PipeRunMode

    # The ``--mock-inference`` trigger (the thin reportable-mock kept by eng review D8): a LIVE run
    # whose LLM leaf calls are faked with *non-zero* synthetic usage so a cost report renders —
    # unlike ``run_mode=DRY`` whose zero-token usage is suppressed. This is the cheap, deterministic
    # cross-worker cost-report validation affordance. Single writer:
    # ``PipeRunParamsFactory.make_run_params`` (fed by ``prepare_pipe_job`` off the CLI flag).
    # Non-LLM leaves have no reportable mock and fail loud (``MockInferenceUnsupportedError``).
    is_mock_inference: bool = False

    @property
    def is_mock_built(self) -> bool:
        """True when the leaf output is a synthetic mock (either trigger) — arms the object-fidelity guard."""
        return self.run_mode.is_dry or self.is_mock_inference
