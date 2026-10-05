"""The typed flow of a PipeSequence: what each name in working memory holds, step by step, as a stuff spec.

The flow is built in step order. The sequence's declared inputs seed it; a pipe step's `result` takes its
pipe's output spec, made plural by `batch_over`, `nb_output` or `multiple_output`; a binding step contributes
the spec it derives. A pipe step also contributes what its pipe stores on the memory it runs on besides its
result (`PipeAbstract.memory_writes`): a nested sequence's steps and a condition's outcome run on the caller's
memory, and a PipeParallel with `add_each_output` stores each branch's result there. A name a later step
stores replaces what was there, so a binding's root is typed by the latest value stored under it.

It is used in three places, and only these: a binding types its root from the flow, a step reading a
binding's result is checked against the spec the binding derives, and a binding ending the sequence is
checked against the sequence's output. Extending the check to every step's inputs is a separate change.
"""

from typing import NamedTuple

from pydantic import BaseModel, ConfigDict

from pipelex.core.concepts.concept import Concept
from pipelex.core.pipes.exceptions import PipeValidationError
from pipelex.core.pipes.inputs.input_stuff_specs import InputStuffSpecs
from pipelex.core.pipes.stuff_spec.stuff_spec import StuffSpec
from pipelex.interpreter_hub import get_concept_library, get_optional_pipe
from pipelex.libraries.concept.concept_library_abstract import ConceptLibraryAbstract
from pipelex.libraries.concept.exceptions import ConceptLibraryError
from pipelex.pipe_controllers.binding.binding_concept_resolvers import LibraryConceptWalkResolver, library_concept_key
from pipelex.pipe_controllers.binding.binding_derivation import BindingDerivation, BindingRoot, derive_binding
from pipelex.pipe_controllers.binding.binding_step import BindingStep
from pipelex.pipe_controllers.binding.exceptions import BindingPathUnresolvedError
from pipelex.pipe_controllers.sub_pipe import SubPipe
from pipelex.validation_error_types import PipeValidationErrorType

# A step of a PipeSequence, as the runtime holds it: a pipe step or a binding step.
SequenceStep = SubPipe | BindingStep


class FlowSlot(BaseModel):
    """What a name holds at a point of the flow, and which binding step stored it, if one did."""

    model_config = ConfigDict(frozen=True)

    # `None` when the flow cannot type the value: a pipe that does not resolve (an unloaded dependency) stored it, or the
    # outcomes of a condition store it under different specs.
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
    # The slots the steps stored, as they stand after the last step: what the sequence leaves in the memory it runs on.
    written_slots: dict[str, FlowSlot]


class DerivedBinding(NamedTuple):
    """What a binding step binds: the derivation of its path, and the spec of the value it stores."""

    derivation: BindingDerivation
    stuff_spec: StuffSpec


def resolve_library_concept(*, concept_library: ConceptLibraryAbstract, concept_ref: str) -> Concept | None:
    """The library's concept for a ref, looked up directly, then among a dependency's aliased keys when one alone matches."""
    try:
        return concept_library.get_required_concept(concept_ref=concept_ref)
    except ConceptLibraryError:
        candidate_keys = concept_library.list_concept_keys_for_ref(concept_ref=concept_ref)
        if len(candidate_keys) != 1:
            return None
        return concept_library.get_required_concept(concept_ref=candidate_keys[0])


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


def derive_binding_spec(*, binding_step: BindingStep, root_spec: StuffSpec, sequence_code: str, domain_code: str) -> DerivedBinding:
    """Derive what a binding step binds from the spec of its root.

    Raises:
        PipeValidationError: ``BINDING_PATH_UNRESOLVED`` when the path cannot be walked from the root's concept, or when the
            concept it derives is not in the library.
    """
    concept_library = get_concept_library()
    try:
        # The root is walked from the key the library holds its concept under, which for a dependency package's
        # concept names the package, so the package's own definitions are read and never a host's of the same spelling.
        root_concept_key = library_concept_key(concept_library=concept_library, concept=root_spec.concept)
        derivation = derive_binding(
            path=binding_step.from_path,
            root=BindingRoot(concept_ref=root_concept_key, multiplicity=root_spec.multiplicity),
            resolver=LibraryConceptWalkResolver(concept_library=concept_library),
        )
    except BindingPathUnresolvedError as exc:
        raise binding_path_unresolved_error(sequence_code=sequence_code, domain_code=domain_code, binding_step=binding_step, exc=exc) from exc
    result_concept: Concept | None
    if derivation.is_bare_name:
        result_concept = root_spec.concept
    else:
        result_concept = resolve_library_concept(concept_library=concept_library, concept_ref=derivation.concept_ref)
    if result_concept is None:
        missing_exc = BindingPathUnresolvedError(
            f"Cannot bind '{binding_step.from_path}': the concept it derives, '{derivation.concept_ref}', is not in the library.",
            path=binding_step.from_path,
            failed_segment=binding_step.from_path.rsplit(".", maxsplit=1)[-1],
            available_fields=[],
        )
        raise binding_path_unresolved_error(sequence_code=sequence_code, domain_code=domain_code, binding_step=binding_step, exc=missing_exc)
    return DerivedBinding(derivation=derivation, stuff_spec=StuffSpec(concept=result_concept, multiplicity=derivation.multiplicity))


def build_sequence_typed_flow(
    *,
    steps: list[SequenceStep],
    declared_inputs: InputStuffSpecs,
    sequence_code: str,
    domain_code: str,
    visited_pipes: set[str],
) -> SequenceTypedFlow:
    """Build the typed flow of a sequence's steps, deriving every binding whose root it types.

    Args:
        steps: The sequence's steps, in order.
        declared_inputs: The sequence's declared inputs, which seed the flow.
        sequence_code: The sequence's code, for messages.
        domain_code: The sequence's domain, for messages.
        visited_pipes: The `visit_key` of each pipe whose flow is being built, the sequence's own included, so a pipe
            reached again through its own steps contributes nothing more.

    Raises:
        PipeValidationError: ``BINDING_PATH_UNRESOLVED`` when a binding's path cannot be walked from its root's concept,
            or when the concept it derives is not in the library.
    """
    slots: dict[str, FlowSlot] = {name: FlowSlot(stuff_spec=stuff_spec) for name, stuff_spec in declared_inputs.root.items()}
    written_names: set[str] = set()
    binding_derivations: dict[int, BindingDerivation] = {}
    binding_specs: dict[int, StuffSpec] = {}
    binding_slots_by_pipe_step: dict[int, dict[str, FlowSlot]] = {}

    for step_index, step in enumerate(steps):
        if isinstance(step, BindingStep):
            written_names.add(step.output_name)
            root_slot = slots.get(step.root_name)
            if root_slot is None or root_slot.stuff_spec is None:
                # A root nothing types: an undeclared one, refused as a missing input of the sequence; the result of a pipe
                # that does not resolve, assumed to deliver as the rest of the sequence's checks assume; or a name the
                # outcomes of a condition store under different specs, which the run derives from the value it holds.
                slots[step.output_name] = FlowSlot(stuff_spec=None, binding_step_index=step_index)
                continue
            derived_binding = derive_binding_spec(
                binding_step=step, root_spec=root_slot.stuff_spec, sequence_code=sequence_code, domain_code=domain_code
            )
            binding_derivations[step_index] = derived_binding.derivation
            binding_specs[step_index] = derived_binding.stuff_spec
            slots[step.output_name] = FlowSlot(stuff_spec=derived_binding.stuff_spec, binding_step_index=step_index)
            continue

        binding_slots_by_pipe_step[step_index] = {name: slot for name, slot in slots.items() if slot.binding_step_index is not None}
        step_pipe = get_optional_pipe(pipe_code=step.pipe_code)
        if step_pipe is None:
            if step.output_name:
                written_names.add(step.output_name)
                slots[step.output_name] = FlowSlot(stuff_spec=None)
            continue
        if step.batch_params is None:
            # A batched step runs its pipe on a copy of the memory for each item, so only its result comes back.
            for written_name, written_spec in step_pipe.memory_writes(visited_pipes=visited_pipes).items():
                written_names.add(written_name)
                slots[written_name] = FlowSlot(stuff_spec=written_spec)
        if step.output_name:
            written_names.add(step.output_name)
            slots[step.output_name] = FlowSlot(stuff_spec=step.result_spec(step_pipe=step_pipe))

    return SequenceTypedFlow(
        binding_derivations=binding_derivations,
        binding_specs=binding_specs,
        binding_slots_by_pipe_step=binding_slots_by_pipe_step,
        final_slots=slots,
        written_slots={name: slot for name, slot in slots.items() if name in written_names},
    )
