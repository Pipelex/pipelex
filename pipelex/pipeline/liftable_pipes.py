"""Liftable-pipe inventory (`liftable_pipes`) for the validate surfaces.

Implicit lifting (optionals design D3) means a pipe with a plain input fed by a maybe-absent
slot is silently skipped at run time. The phase-1 commitment that makes this acceptable is
build-time visibility: the valid report lists every pipe that may be lifted, with the slots
whose absence triggers the skip and the absence source — structured data beside
`pipe_io_contracts`, keyed the same way (namespaced `pipe_ref`).
"""

from collections.abc import Sequence

from pydantic import BaseModel, Field

from pipelex.pipeline.controller_taint import ControllerTaintAnalysis


class LiftablePipeEntry(BaseModel):
    """One pipe that may be skipped (lifted) when an optional slot resolves absent."""

    pipe_ref: str
    """Namespaced ref of the liftable pipe."""

    within_pipe_ref: str
    """Namespaced ref of the controller in whose flow the lift happens."""

    skipped_when_absent: list[str] = Field(default_factory=list)
    """The slot names whose absence lifts the pipe."""

    absence_source: str
    """Where the possible absence originates (human-readable)."""


def build_liftable_pipes(taint_analyses: Sequence[ControllerTaintAnalysis]) -> list[LiftablePipeEntry]:
    """Project the controllers' taint analyses into `liftable_pipes` entries.

    Sequences contribute their lifted steps; parallels contribute their liftable branches
    (a parallel nested in a sequence reports its branches under itself, so there is no
    double-reporting).

    Args:
        taint_analyses: The controllers' analyses from `collect_controller_taint_analyses`
            (one taint walk per validate pass, shared with `build_optionality_warnings`).

    Returns:
        Entries in deterministic order (by controller ref, then flow order).
    """
    entries: list[LiftablePipeEntry] = []
    for taint_analysis in taint_analyses:
        for liftable_step in taint_analysis.liftable_steps:
            entries.append(
                LiftablePipeEntry(
                    pipe_ref=liftable_step.pipe_ref,
                    within_pipe_ref=liftable_step.within_pipe_ref,
                    skipped_when_absent=list(liftable_step.trigger_variable_names),
                    absence_source=liftable_step.absence_source,
                ),
            )
    return entries
