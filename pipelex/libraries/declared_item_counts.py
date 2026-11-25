"""The load's check of the item counts a pipe declares, against the maximum in force.

A pipe declares a fixed number of items with `Concept[N]` on an input or its output, and a controller declares one for
a step with `nb_output = N`, which reaches a `PipeLLM` as its `fixed_nb_output` and a `PipeImgGen` as its `nb_images`.
The library load reads every one of them before it builds anything, and refuses a pipe declaring more items for one slot
than the maximum in force (`pipelex.core.pipes.declared_item_count`), so a validation never dry-runs it and a run never
starts it.
"""

from pipelex.core.pipes.declared_item_count import ensure_declared_item_count_allowed
from pipelex.core.pipes.variable_multiplicity import fixed_item_count, parse_concept_with_multiplicity
from pipelex.pipe_controllers.parallel.pipe_parallel_blueprint import PipeParallelBlueprint
from pipelex.pipe_controllers.sequence.pipe_sequence_blueprint import PipeSequenceBlueprint
from pipelex.pipe_controllers.sub_pipe_blueprint import SubPipeBlueprint
from pipelex.pipe_machinery.pipe_blueprint import PipeBlueprint, slot_concept_spec


def _steps_of(*, blueprint: PipeBlueprint) -> list[SubPipeBlueprint]:
    """The steps of a controller that may set `nb_output`: a sequence's pipe steps and a parallel's branches."""
    if isinstance(blueprint, PipeSequenceBlueprint):
        return blueprint.pipe_steps
    if isinstance(blueprint, PipeParallelBlueprint):
        return list(blueprint.branches)
    return []


def ensure_pipe_declared_item_counts_allowed(*, pipe_code: str, blueprint: PipeBlueprint, maximum: int) -> None:
    """Refuse a pipe declaring more items for one of its slots than `maximum`: an input, its output or a step's `nb_output`.

    Args:
        pipe_code: The pipe's code, which the refusal's slot names.
        blueprint: The pipe's blueprint, whose specs already passed the parser, so every count in them is a number.
        maximum: The maximum in force.

    Raises:
        DeclaredItemCountLimitError: One of the pipe's counts passes the maximum; the first found is named.
    """
    for input_name, slot_value in (blueprint.inputs or {}).items():
        input_count = fixed_item_count(multiplicity=parse_concept_with_multiplicity(slot_concept_spec(slot_value)).multiplicity)
        if input_count is not None:
            ensure_declared_item_count_allowed(count=input_count, slot=f"the input '{input_name}' of the pipe '{pipe_code}'", maximum=maximum)
    output_count = fixed_item_count(multiplicity=parse_concept_with_multiplicity(blueprint.output).multiplicity)
    if output_count is not None:
        ensure_declared_item_count_allowed(count=output_count, slot=f"the output of the pipe '{pipe_code}'", maximum=maximum)
    for step in _steps_of(blueprint=blueprint):
        if step.nb_output is not None:
            ensure_declared_item_count_allowed(
                count=step.nb_output,
                slot=f"the {step.step_label} in the pipe '{pipe_code}'",
                maximum=maximum,
            )
