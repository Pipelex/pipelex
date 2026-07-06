"""Single-pass controller taint collection shared by the validate-report projections.

The absence-taint walk (`PipeSequence.analyze_taint`, `PipeParallel.analyze_branch_taint`)
hub-resolves every sub-pipe and recurses through nested controllers, so it must run exactly
once per validate pass. Both report projections — the `liftable_pipes` inventory and the
`warnings` optionality lints — consume the same analyses; callers collect them here and feed
the list to both builders instead of each builder re-walking the pipes.

Must run while the validation library is loaded — the analyses resolve child pipes through
the hub.
"""

from collections.abc import Sequence
from typing import TypeAlias

from pipelex.core.pipes.pipe_abstract import PipeAbstract
from pipelex.pipe_controllers.absence_taint import ParallelTaintAnalysis, SequenceTaintAnalysis
from pipelex.pipe_controllers.parallel.pipe_parallel import PipeParallel
from pipelex.pipe_controllers.sequence.pipe_sequence import PipeSequence

ControllerTaintAnalysis: TypeAlias = SequenceTaintAnalysis | ParallelTaintAnalysis


def collect_controller_taint_analyses(pipes: Sequence[PipeAbstract]) -> list[ControllerTaintAnalysis]:
    """Run each controller's absence-taint analysis once, in deterministic order (by pipe_ref).

    Args:
        pipes: The loaded pipes to analyze (typically `ValidateBundleResult.pipes`).

    Returns:
        One analysis per controller pipe, ordered by the controller's `pipe_ref`.
    """
    analyses: list[ControllerTaintAnalysis] = []
    for pipe in sorted(pipes, key=lambda loaded_pipe: loaded_pipe.pipe_ref):
        if isinstance(pipe, PipeSequence):
            analyses.append(pipe.analyze_taint())
        elif isinstance(pipe, PipeParallel):
            analyses.append(pipe.analyze_branch_taint())
    return analyses
