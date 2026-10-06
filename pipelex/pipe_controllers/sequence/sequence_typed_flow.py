"""The typed flow of a PipeSequence: what each name in working memory holds, step by step, as a stuff spec.

The flow is built in step order. The sequence's declared inputs seed it; a pipe step's `result` takes its
pipe's output spec, made plural by `batch_over`, `nb_output` or `multiple_output`; a binding step contributes
the spec it derives. A pipe step also contributes what its pipe stores on the memory it runs on besides its
result (`step_memory_writes`): a nested sequence's steps and a condition's outcome run on the caller's
memory, and a PipeParallel with `add_each_output` stores each branch's result there. A name a later step
always stores replaces what was there, so a binding's root is typed by the latest value stored under it; a
name a step stores on some runs only, as a condition whose `continue` outcome stores nothing, keeps its spec
when the value stored has the same one, and is untyped otherwise.

A binding's root is untyped in two ways. The values it may hold have different specs, as the outcomes of a
condition storing it under different concepts: that is seen before the run (`SpecDisagreement`), so the
binding is refused as `binding_path_unresolved`. Or a pipe that does not resolve at validation, a dependency
not loaded yet, stored it: nothing can type it before the run, so the binding is assumed to deliver and the
run derives it from the value it holds, checking it there against what reads it.

`step_memory_writes` is the one place a step's stores beside its result are computed: the sequence's needed
inputs and its absence-taint walk read them from it too, so the three analyses agree on every name.

The flow serves three checks: a binding types its root from it, every pipe step is checked against the spec
the flow carries for each name its pipe declares, whichever declared input, pipe step or binding put it there,
and a binding ending the sequence is checked against the sequence's output.

A pipe step's result is typed by the output its pipe declares. A pipe declaring `Anything` or `Dynamic`, as a
condition whose outcomes produce different concepts must, stores a value whose concept is known only when it
runs, so a step reading it is assumed to get the concept it reads, as from a pipe that does not resolve. The
flow keeps what stored each value (`FlowSlot.is_stored_by_pipe_step`), and so does each value a disagreement
lists (`StoredSpec.is_stored_by_pipe_step`), so a declared input or a binding's value a step may leave in
place is checked as any other, whatever spec it holds.
"""

from typing import Any, NamedTuple, Self

from pydantic import BaseModel, ConfigDict, Field
from typing_extensions import override

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
from pipelex.pipe_machinery.memory_writes import MemoryWrite, SpecDisagreement, is_same_value_spec, possible_values
from pipelex.pipe_machinery.pipe_abstract import PipeAbstract
from pipelex.validation_error_types import PipeValidationErrorType

# A step of a PipeSequence, as the runtime holds it: a pipe step or a binding step.
SequenceStep = SubPipe | BindingStep


class FlowSlot(BaseModel):
    """What a name holds at a point of the flow, which step stored it, and which binding step, if one did."""

    model_config = ConfigDict(frozen=True)

    # `None` when the flow cannot type the value: a pipe that does not resolve (an unloaded dependency) stored it, or the
    # values it may hold have different specs, which `disagreement` then says.
    stuff_spec: StuffSpec | None
    binding_step_index: int | None = None
    # Set only when `stuff_spec` is `None` because the values the name may hold have different specs, seen before the run.
    disagreement: SpecDisagreement | None = None
    # The index of the step that stored the value, as its result or as a name its pipe stores besides, `None` for a value
    # the sequence's caller passed in, one of its declared inputs.
    producer_step_index: int | None = None

    @property
    def is_stored_by_pipe_step(self) -> bool:
        """Whether a pipe step stored the value, as its result or as a name its pipe stores besides, rather than the sequence's
        caller under a declared input or a binding step.

        The concept of a value a pipe step stored as `Anything` or `Dynamic` is known only when it runs, so a step reading it is
        assumed to get the concept it reads. A declared input is a contract the caller is held to, and a binding derives its
        concept from a path, so a value either one put there is checked as any other.
        """
        return self.producer_step_index is not None and self.binding_step_index is None


class SequenceTypedFlow(BaseModel):
    """The typed flow of one sequence: the derivation of each binding step, and what each pipe step can read."""

    model_config = ConfigDict(frozen=True)

    # By step index, for each binding step whose root the flow types.
    binding_derivations: dict[int, BindingDerivation]
    # By step index, the derived spec of each binding step whose root the flow types.
    binding_specs: dict[int, StuffSpec]
    # By pipe-step index, every slot visible when the step runs: the declared inputs and what earlier steps stored.
    slots_by_pipe_step: dict[int, dict[str, FlowSlot]]
    # The flow after the last step.
    final_slots: dict[str, FlowSlot]
    # The slots the steps stored, as they stand after the last step: what the sequence leaves in the memory it runs on.
    written_slots: dict[str, FlowSlot]
    # The names some step stores on every run, among the written slots.
    always_written_names: frozenset[str]
    # By pipe-step index, what the step stores besides its result (`step_memory_writes`), for the walks that follow the flow.
    memory_writes_by_pipe_step: dict[int, dict[str, MemoryWrite]]


class SequenceFlowMemo(BaseModel):
    """What one PipeSequence derived from one state of the libraries its steps resolve in, kept so it is built once.

    The typed flow and what the sequence stores in its caller's memory depend only on the sequence's own steps and on the
    pipes and concepts they resolve to in the current library, so the memo records the state tokens of the current pipe
    and concept libraries (`library_state`) and is discarded once either differs: a library that loads or removes a pipe or
    a concept, or another library where a pipe code resolves differently, never reads a flow built before.

    A walk that cut a cycle short, having already visited a pipe the sequence reaches, builds a flow that depends on what it
    visited, so only the flows built by a walk that visited none of `reachable_visit_keys` are kept: those are the same
    whatever else the walk visited.

    The memo rests on one assumption: a pipe is never changed in place after it is built, and a changed pipe enters a library
    as a new pipe, which replaces the library's state token.

    A memo is a cache, never part of what its sequence is. Pydantic compares the private attributes of two models, where a
    sequence keeps its memo, so every memo compares equal to every other: two sequences of one definition are equal whatever
    each has derived, and comparing them never walks from a memo to its owner, whose memo it would compare again without end.
    A sequence holds a memo from its creation, an empty one that is valid for no sequence, so that no comparison weighs a memo
    against none. A copy of a memo, by `copy`, `deepcopy` or pickling, is empty.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    # The sequence that built the memo, `None` for an empty memo, compared by identity only. A shallow copy of the sequence
    # shares the memo object, and must not read it.
    owner: Any = Field(default=None, repr=False)
    # The state tokens of the pipe library and of the concept library the memo was built in, `(0, 0)` for an empty memo: no
    # library state has the token 0.
    library_state: tuple[int, int] = (0, 0)
    # The `visit_key` of every pipe the sequence reaches through its steps, at any depth, itself excepted.
    reachable_visit_keys: frozenset[str] | None = None
    typed_flow: SequenceTypedFlow | None = None
    memory_writes: dict[str, MemoryWrite] | None = None
    # The declared inputs the check of each step accepts for every pipe step reading the caller's value under them.
    accepted_declared_names: frozenset[str] | None = None

    def is_valid_for(self, *, owner: object, library_state: tuple[int, int]) -> bool:
        return self.owner is owner and self.library_state == library_state

    @override
    def __eq__(self, other: object) -> bool:
        """Every memo equals every other, so that what a sequence derived never takes part in what it equals."""
        if isinstance(other, SequenceFlowMemo):
            return True
        return NotImplemented

    # A memo is never hashed, as the sequence holding it, a mutable model, is not. Python's own idiom for an unhashable class
    # beside its `__eq__`, which mypy reads as an override of `object.__hash__`.
    __hash__ = None  # type: ignore[assignment]

    @override
    def __copy__(self) -> Self:
        """A copy is empty: what the memo derived belongs to the sequence that built it."""
        return self.__class__()

    @override
    def __deepcopy__(self, memo: dict[int, Any] | None = None) -> Self:
        """A copy is empty, and never copies the sequence that owns the memo, which would copy the memo again."""
        return self.__class__()

    @override
    def __reduce__(self) -> tuple[type[Self], tuple[()]]:
        """A pickled memo comes back empty, as a copy does: the sequence unpickled beside it never built what it derived."""
        return (self.__class__, ())


class DerivedBinding(NamedTuple):
    """What a binding step binds: the derivation of its path, and the spec of the value it stores."""

    derivation: BindingDerivation
    stuff_spec: StuffSpec


def authored_step_number(*, steps: list[SequenceStep], step_index: int) -> int:
    """The number of a step, counting from 1, as its author wrote the sequence.

    The binding a sequence writes for a dotted `batch_over` is no step of the author's: it shares the number of the pipe
    step it was written for, which follows it.
    """
    rewritten_before = sum(1 for step in steps[:step_index] if isinstance(step, BindingStep) and step.is_dotted_batch_over)
    return step_index + 1 - rewritten_before


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
    msg = f"In pipe '{sequence_code}', the {binding_step.label} cannot be derived. {exc}"
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


def step_memory_writes(*, step: SubPipe, step_pipe: PipeAbstract, visited_pipes: set[str]) -> dict[str, MemoryWrite]:
    """What a pipe step stores in the sequence's memory besides its result, as the typed flow, the needed inputs and the
    absence-taint walk of the sequence all read it.

    The step's pipe stores its `memory_writes`, unless the step batches: a batched step runs its pipe on a copy of the
    memory for each item, so only its result comes back.
    """
    if step.batch_params is not None:
        return {}
    return step_pipe.memory_writes(visited_pipes=visited_pipes)


def slot_after_write(*, prior_slot: FlowSlot | None, memory_write: MemoryWrite, step_index: int, step_label: str) -> FlowSlot:
    """What a name holds once a step stored it: the stored spec, or, when the step may leave the name as it was, the spec
    the stored value and the value already there agree on, untyped when they do not.

    A name left untyped records why when both sides are seen before the run, each typed or carrying a disagreement already:
    the disagreement lists every value of both sides, so that a step reading the name is checked against each. A side nothing
    could type, a pipe that does not resolve having stored it, leaves the name untyped with only the other side's disagreement,
    if it carries one. The value held before keeps what stored it, so a declared input or a binding's value the step may leave
    in place is still read as one (`StoredSpec.is_stored_by_pipe_step`). `step_index` is the storing step's, and `step_label`
    names it for that record, e.g. "step 2 (pipe 'swap_record')".
    """
    if memory_write.is_always_written or prior_slot is None:
        return FlowSlot(stuff_spec=memory_write.stuff_spec, disagreement=memory_write.disagreement, producer_step_index=step_index)
    if is_same_value_spec(first_spec=prior_slot.stuff_spec, second_spec=memory_write.stuff_spec):
        return prior_slot
    prior_values = possible_values(
        stored_by=f"the value it held before {step_label}, which the step leaves when it stores nothing,",
        stuff_spec=prior_slot.stuff_spec,
        disagreement=prior_slot.disagreement,
        is_stored_by_pipe_step=prior_slot.is_stored_by_pipe_step,
    )
    written_values = possible_values(
        stored_by=f"{step_label}, when it stores a value,",
        stuff_spec=memory_write.stuff_spec,
        disagreement=memory_write.disagreement,
        is_stored_by_pipe_step=True,
    )
    disagreement: SpecDisagreement | None
    if prior_values is None or written_values is None:
        disagreement = prior_slot.disagreement or memory_write.disagreement
    else:
        disagreement = SpecDisagreement(stored_specs=prior_values + written_values)
    return FlowSlot(stuff_spec=None, disagreement=disagreement, producer_step_index=step_index)


def untyped_root_error(*, sequence_code: str, domain_code: str, binding_step: BindingStep, disagreement: SpecDisagreement) -> PipeValidationError:
    """The refusal of a binding whose root's values have different specs, so that its concept is not known before the run."""
    root_name = binding_step.root_name
    msg = (
        f"Cannot bind '{binding_step.from_path}': the concept of '{root_name}' is not known before the run, because the outcomes that may "
        f"store it store it under different concepts: {disagreement.describe(relative_to_domain=domain_code)}. Store '{root_name}' under "
        "one concept in every outcome, or bind inside each outcome, where its concept is known."
    )
    exc = BindingPathUnresolvedError(msg, path=binding_step.from_path, failed_segment=root_name, available_fields=[])
    return binding_path_unresolved_error(sequence_code=sequence_code, domain_code=domain_code, binding_step=binding_step, exc=exc)


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
            when the concept it derives is not in the library, or when the values its root may hold have different specs.
    """
    slots: dict[str, FlowSlot] = {name: FlowSlot(stuff_spec=stuff_spec) for name, stuff_spec in declared_inputs.root.items()}
    written_names: set[str] = set()
    always_written_names: set[str] = set()
    binding_derivations: dict[int, BindingDerivation] = {}
    binding_specs: dict[int, StuffSpec] = {}
    slots_by_pipe_step: dict[int, dict[str, FlowSlot]] = {}
    memory_writes_by_pipe_step: dict[int, dict[str, MemoryWrite]] = {}

    for step_index, step in enumerate(steps):
        if isinstance(step, BindingStep):
            written_names.add(step.output_name)
            always_written_names.add(step.output_name)
            root_slot = slots.get(step.root_name)
            if root_slot is not None and root_slot.disagreement is not None:
                raise untyped_root_error(sequence_code=sequence_code, domain_code=domain_code, binding_step=step, disagreement=root_slot.disagreement)
            if root_slot is None or root_slot.stuff_spec is None:
                # A root nothing types: an undeclared one, refused as a missing input of the sequence; or a value a pipe that
                # does not resolve stored, assumed to deliver as the rest of the sequence's checks assume, which the run
                # derives from the value it holds and checks against what reads it.
                slots[step.output_name] = FlowSlot(stuff_spec=None, binding_step_index=step_index, producer_step_index=step_index)
                continue
            derived_binding = derive_binding_spec(
                binding_step=step, root_spec=root_slot.stuff_spec, sequence_code=sequence_code, domain_code=domain_code
            )
            binding_derivations[step_index] = derived_binding.derivation
            binding_specs[step_index] = derived_binding.stuff_spec
            slots[step.output_name] = FlowSlot(stuff_spec=derived_binding.stuff_spec, binding_step_index=step_index, producer_step_index=step_index)
            continue

        slots_by_pipe_step[step_index] = dict(slots)
        step_pipe = get_optional_pipe(pipe_code=step.pipe_code)
        if step_pipe is None:
            if step.output_name:
                written_names.add(step.output_name)
                always_written_names.add(step.output_name)
                slots[step.output_name] = FlowSlot(stuff_spec=None, producer_step_index=step_index)
            continue
        step_writes = step_memory_writes(step=step, step_pipe=step_pipe, visited_pipes=visited_pipes)
        memory_writes_by_pipe_step[step_index] = step_writes
        step_label = f"step {authored_step_number(steps=steps, step_index=step_index)} (pipe '{step_pipe.code}')"
        for written_name, memory_write in step_writes.items():
            written_names.add(written_name)
            if memory_write.is_always_written:
                always_written_names.add(written_name)
            slots[written_name] = slot_after_write(
                prior_slot=slots.get(written_name), memory_write=memory_write, step_index=step_index, step_label=step_label
            )
        if step.output_name:
            written_names.add(step.output_name)
            always_written_names.add(step.output_name)
            slots[step.output_name] = FlowSlot(stuff_spec=step.result_spec(step_pipe=step_pipe), producer_step_index=step_index)

    return SequenceTypedFlow(
        binding_derivations=binding_derivations,
        binding_specs=binding_specs,
        slots_by_pipe_step=slots_by_pipe_step,
        final_slots=slots,
        written_slots={name: slot for name, slot in slots.items() if name in written_names},
        always_written_names=frozenset(always_written_names),
        memory_writes_by_pipe_step=memory_writes_by_pipe_step,
    )
