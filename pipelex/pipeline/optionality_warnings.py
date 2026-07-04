"""Advisory optionality lints (`warnings`) for the validate surfaces.

The validation report's `warnings` array carries findings that are worth surfacing on a VALID
bundle but must never flip `is_valid`. The first occupant is the useless-`!` lint
(`optional_force_redundant`): a `!` (force) input asserts at run time that a maybe-absent slot
is present — but when every analyzed flow guarantees the slot, the assertion can never fire and
the marker is dead weight.

The presence data comes from the same controller taint analyses that feed the liftable-pipe
inventory (`PipeSequence.analyze_taint`, `PipeParallel.analyze_branch_taint`). Observations are
aggregated per (pipe, variable) ACROSS flows before warning: a pipe whose `!` is meaningful in
one flow is never told to remove it just because another flow guarantees the slot. A `!` input
on a pipe that appears in no analyzed flow yields no observation and no warning (conservative —
there is no flow context to judge it in).

The over-claimed-`?` lint (a `?` output that can never produce absence) is deliberately NOT
emitted in phase 1: D5 blesses over-claiming as signature-evolution room.
"""

from collections.abc import Sequence
from typing import TYPE_CHECKING

from pipelex.base_exceptions import ValidationErrorCategory, ValidationErrorItem
from pipelex.core.pipes.exceptions import PipeValidationErrorType
from pipelex.core.pipes.pipe_abstract import PipeAbstract
from pipelex.pipe_controllers.parallel.pipe_parallel import PipeParallel
from pipelex.pipe_controllers.sequence.pipe_sequence import PipeSequence

if TYPE_CHECKING:
    from pipelex.pipe_controllers.absence_taint import ForceConsumptionInfo


def build_optionality_warnings(pipes: Sequence[PipeAbstract]) -> list[ValidationErrorItem]:
    """Project the controllers' taint analyses into advisory `warnings` items.

    Must run while the validation library is loaded — the analyses resolve child pipes
    through the hub (same requirement as `build_liftable_pipes`).

    Args:
        pipes: The loaded pipes to analyze (typically `ValidateBundleResult.pipes`).

    Returns:
        One `optional_force_redundant` item per (pipe, `!`-input) whose slot is guaranteed
        present in every analyzed flow, in deterministic order (by pipe_ref, then variable).
    """
    observations: list[ForceConsumptionInfo] = []
    for pipe in sorted(pipes, key=lambda loaded_pipe: loaded_pipe.pipe_ref):
        if isinstance(pipe, PipeSequence):
            observations.extend(pipe.analyze_taint().force_consumptions)
        elif isinstance(pipe, PipeParallel):
            observations.extend(pipe.analyze_branch_taint().force_consumptions)

    asserted: set[tuple[str, str]] = set()
    redundant: dict[tuple[str, str], list[ForceConsumptionInfo]] = {}
    for observation in observations:
        consumption_key = (observation.pipe_ref, observation.variable_name)
        if observation.is_asserting:
            asserted.add(consumption_key)
        else:
            redundant.setdefault(consumption_key, []).append(observation)

    warnings: list[ValidationErrorItem] = []
    for consumption_key in sorted(redundant):
        if consumption_key in asserted:
            continue
        pipe_ref, variable_name = consumption_key
        domain_code, _, pipe_code = pipe_ref.partition(".")
        flow_refs = sorted({observation.within_pipe_ref for observation in redundant[consumption_key]})
        flows_desc = ", ".join(f"'{flow_ref}'" for flow_ref in flow_refs)
        message = (
            f"Input '{variable_name}' of pipe '{pipe_ref}' is declared with a force marker ('!'), but the slot is "
            f"guaranteed present in every analyzed flow ({flows_desc}) — the assertion can never fire there. "
            f"Remove the '!' (plain input), unless a flow that feeds it a maybe-absent value is coming."
        )
        warnings.append(
            ValidationErrorItem(
                category=ValidationErrorCategory.PIPE_VALIDATION,
                error_type=PipeValidationErrorType.OPTIONAL_FORCE_REDUNDANT,
                pipe_code=pipe_code,
                domain_code=domain_code,
                variable_names=[variable_name],
                message=message,
            )
        )
    return warnings
