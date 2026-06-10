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

from pydantic import BaseModel

from pipelex.pipe_run.pipe_run_mode import PipeRunMode


class CogtRunParams(BaseModel):
    """Execution-mode contract carried on every cogt assignment (crosses the Temporal wire)."""

    run_mode: PipeRunMode = PipeRunMode.LIVE
