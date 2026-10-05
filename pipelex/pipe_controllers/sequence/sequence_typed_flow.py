"""The typed flow of a PipeSequence: what each name in working memory holds, step by step, as a stuff spec.

The flow is built in step order. The sequence's declared inputs seed it; a pipe step's `result` takes its
pipe's output spec, made plural by `batch_over`, `nb_output` or `multiple_output`; a PipeParallel step with
`add_each_output` contributes each branch's result; a binding step contributes the spec it derives. A name a
later step stores replaces what was there, so a binding's root is typed by the latest value stored under it.

It is used in three places, and only these: a binding types its root from the flow, a step reading a
binding's result is checked against the spec the binding derives, and a binding ending the sequence is
checked against the sequence's output. Extending the check to every step's inputs is a separate change.
"""

from pydantic import BaseModel, ConfigDict

from pipelex.core.concepts.concept import Concept
from pipelex.core.pipes.exceptions import PipeValidationError
from pipelex.core.pipes.inputs.input_stuff_specs import InputStuffSpecs
from pipelex.core.pipes.stuff_spec.stuff_spec import StuffSpec
from pipelex.core.pipes.variable_multiplicity import PresenceMarker, VariableMultiplicity
from pipelex.interpreter_hub import get_concept_library, get_optional_pipe
from pipelex.libraries.concept.concept_library_abstract import ConceptLibraryAbstract
from pipelex.libraries.concept.exceptions import ConceptLibraryError
from pipelex.pipe_controllers.binding.binding_concept_resolvers import LibraryConceptWalkResolver, library_concept_key
from pipelex.pipe_controllers.binding.binding_derivation import BindingDerivation, BindingRoot, derive_binding
from pipelex.pipe_controllers.binding.binding_step import BindingStep
from pipelex.pipe_controllers.binding.exceptions import BindingPathUnresolvedError
from pipelex.pipe_controllers.parallel.pipe_parallel import PipeParallel
from pipelex.pipe_controllers.sub_pipe import SubPipe
from pipelex.pipe_machinery.pipe_abstract import PipeAbstract
from pipelex.pipe_run.pipe_run_params import output_multiplicity_to_apply
from pipelex.validation_error_types import PipeValidationErrorType

# A step of a PipeSequence, as the runtime holds it: a pipe step or a binding step.
SequenceStep = SubPipe | BindingStep


class FlowSlot(BaseModel):
    """What a name holds at a point of the flow, and which binding step stored it, if one did."""

    model_config = ConfigDict(frozen=True)

    # `None` when the flow cannot type the value: a pipe that does not resolve (an unloaded dependency) stored it.
    stuff_spec: StuffSpec | None
    binding_step_index: int | None = None


class SequenceTypedFlow(BaseModel):
    """The typed flow of one sequence: the derivation of each binding step, and what each pipe step can read."""

    model_config = ConfigDict(frozen=True)

    # By step index, for each binding step whose root the flow types.
    binding_derivations: dict[int, BindingDerivation]
    # By step index, the derived spec of each binding step whose root the flow types.
    binding_specs: dict[int, StuffSpec]
    # By pipe-step index, the slots a binding step stored that are still visible when the step runs.
    binding_slots_by_pipe_step: dict[int, dict[str, FlowSlot]]
    # The flow after the last step.
    final_slots: dict[str, FlowSlot]


def resolve_library_concept(*, concept_library: ConceptLibraryAbstract, concept_ref: str) -> Concept | None:
    """The library's concept for a ref, looked up directly, then among a dependency's aliased keys when one alone matches."""
    try:
        return concept_library.get_required_concept(concept_ref=concept_ref)
    except ConceptLibraryError:
        candidate_keys = concept_library.list_concept_keys_for_ref(concept_ref=concept_ref)
        if len(candidate_keys) != 1:
            return None
        return concept_library.get_required_concept(concept_ref=candidate_keys[0])


def pipe_step_output_spec(*, sub_pipe: SubPipe, step_pipe: PipeAbstract) -> StuffSpec:
    """The spec a pipe step stores under its `result`, resolved the way the run path resolves it."""
    multiplicity_resolution = output_multiplicity_to_apply(
        base_multiplicity=step_pipe.output.multiplicity,
        override_multiplicity=sub_pipe.output_multiplicity,
    )
    multiplicity: VariableMultiplicity | None
    if not multiplicity_resolution.is_multiple_outputs_enabled:
        multiplicity = None
    elif multiplicity_resolution.specific_output_count is not None:
        multiplicity = multiplicity_resolution.specific_output_count
    else:
        multiplicity = True
    presence = step_pipe.output.presence if multiplicity is None else PresenceMarker.PLAIN
    return StuffSpec(concept=step_pipe.output.concept, multiplicity=multiplicity, presence=presence)


def binding_path_unresolved_error(
    *, sequence_code: str, domain_code: str, binding_step: BindingStep, exc: BindingPathUnresolvedError
) -> PipeValidationError:
    msg = f"In pipe '{sequence_code}', the binding step {binding_step.as_written} cannot be derived. {exc}"
    return PipeValidationError(
        message=msg,
        error_type=PipeValidationErrorType.BINDING_PATH_UNRESOLVED,
        domain_code=domain_code,
        pipe_code=sequence_code,
        variable_names=[binding_step.from_path],
    )


def build_sequence_typed_flow(
    *,
    steps: list[SequenceStep],
    declared_inputs: InputStuffSpecs,
    sequence_code: str,
    domain_code: str,
) -> SequenceTypedFlow:
    """Build the typed flow of a sequence's steps, deriving every binding whose root it types.

    Raises:
        PipeValidationError: ``BINDING_PATH_UNRESOLVED`` when a binding's path cannot be walked from its root's concept,
            or when the concept it derives is not in the library.
    """
    concept_library = get_concept_library()
    resolver = LibraryConceptWalkResolver(concept_library=concept_library)
    slots: dict[str, FlowSlot] = {name: FlowSlot(stuff_spec=stuff_spec) for name, stuff_spec in declared_inputs.root.items()}
    binding_derivations: dict[int, BindingDerivation] = {}
    binding_specs: dict[int, StuffSpec] = {}
    binding_slots_by_pipe_step: dict[int, dict[str, FlowSlot]] = {}

    for step_index, step in enumerate(steps):
        if isinstance(step, BindingStep):
            root_slot = slots.get(step.root_name)
            if root_slot is None or root_slot.stuff_spec is None:
                # A root nothing types: an undeclared one, refused as a missing input of the sequence, or the result of
                # a pipe that does not resolve, assumed to deliver as the rest of the sequence's checks assume.
                slots[step.output_name] = FlowSlot(stuff_spec=None, binding_step_index=step_index)
                continue
            root_spec = root_slot.stuff_spec
            try:
                # The root is walked from the key the library holds its concept under, which for a dependency package's
                # concept names the package, so the package's own definitions are read and never a host's of the same spelling.
                root_concept_key = library_concept_key(concept_library=concept_library, concept=root_spec.concept)
                derivation = derive_binding(
                    path=step.from_path,
                    root=BindingRoot(concept_ref=root_concept_key, multiplicity=root_spec.multiplicity),
                    resolver=resolver,
                )
            except BindingPathUnresolvedError as exc:
                raise binding_path_unresolved_error(sequence_code=sequence_code, domain_code=domain_code, binding_step=step, exc=exc) from exc
            result_concept: Concept | None
            if derivation.is_bare_name:
                result_concept = root_spec.concept
            else:
                result_concept = resolve_library_concept(concept_library=concept_library, concept_ref=derivation.concept_ref)
            if result_concept is None:
                missing_exc = BindingPathUnresolvedError(
                    f"Cannot bind '{step.from_path}': the concept it derives, '{derivation.concept_ref}', is not in the library.",
                    path=step.from_path,
                    failed_segment=step.from_path.rsplit(".", maxsplit=1)[-1],
                    available_fields=[],
                )
                raise binding_path_unresolved_error(sequence_code=sequence_code, domain_code=domain_code, binding_step=step, exc=missing_exc)
            binding_spec = StuffSpec(concept=result_concept, multiplicity=derivation.multiplicity)
            binding_derivations[step_index] = derivation
            binding_specs[step_index] = binding_spec
            slots[step.output_name] = FlowSlot(stuff_spec=binding_spec, binding_step_index=step_index)
            continue

        binding_slots_by_pipe_step[step_index] = {name: slot for name, slot in slots.items() if slot.binding_step_index is not None}
        step_pipe = get_optional_pipe(pipe_code=step.pipe_code)
        if step_pipe is None:
            if step.output_name:
                slots[step.output_name] = FlowSlot(stuff_spec=None)
            continue
        if isinstance(step_pipe, PipeParallel) and step_pipe.add_each_output:
            for branch in step_pipe.parallel_sub_pipes:
                if not branch.output_name:
                    continue
                branch_pipe = get_optional_pipe(pipe_code=branch.pipe_code)
                branch_spec = pipe_step_output_spec(sub_pipe=branch, step_pipe=branch_pipe) if branch_pipe is not None else None
                slots[branch.output_name] = FlowSlot(stuff_spec=branch_spec)
        if step.output_name:
            slots[step.output_name] = FlowSlot(stuff_spec=pipe_step_output_spec(sub_pipe=step, step_pipe=step_pipe))

    return SequenceTypedFlow(
        binding_derivations=binding_derivations,
        binding_specs=binding_specs,
        binding_slots_by_pipe_step=binding_slots_by_pipe_step,
        final_slots=slots,
    )
