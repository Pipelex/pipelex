import sys
from typing import TYPE_CHECKING, Any, Literal

from pydantic import PrivateAttr, field_validator
from typing_extensions import override

from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.pipes.exceptions import PipeValidationError
from pipelex.core.pipes.inputs.exceptions import InputStuffSpecNotFoundError
from pipelex.core.pipes.inputs.input_stuff_specs import InputStuffSpecs
from pipelex.core.pipes.inputs.input_stuff_specs_factory import InputStuffSpecsFactory
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.core.pipes.stuff_spec.stuff_spec import StuffSpec
from pipelex.core.pipes.variable_multiplicity import PresenceMarker, VariableMultiplicity, is_multiple_multiplicity, is_multiplicity_compatible
from pipelex.core.qualified_ref import QualifiedRef
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.stuff import Stuff
from pipelex.interpreter_hub import get_concept_library, get_native_concept, get_optional_pipe, get_pipe_library, get_required_pipe
from pipelex.pipe_controllers.absence_taint import (
    ForceConsumptionInfo,
    LiftableStepInfo,
    SequenceTaintAnalysis,
    TaintTriggerScan,
    is_plural_step_result,
    scan_taint_triggers,
)
from pipelex.pipe_controllers.binding.binding_derivation import BindingDerivation
from pipelex.pipe_controllers.binding.binding_step import BindingOutcome, BindingStep
from pipelex.pipe_controllers.binding.exceptions import BindingStepRunError
from pipelex.pipe_controllers.pipe_controller import PipeController
from pipelex.pipe_controllers.sequence.exceptions import PipeSequenceValueError
from pipelex.pipe_controllers.sequence.sequence_typed_flow import (
    DerivedBinding,
    FlowSlot,
    SequenceFlowMemo,
    SequenceStep,
    SequenceTypedFlow,
    authored_step_number,
    build_sequence_typed_flow,
    derive_binding_spec,
    step_memory_writes,
)
from pipelex.pipe_controllers.sub_pipe import SubPipe
from pipelex.pipe_machinery.memory_writes import MemoryWrite, SlotTaint, is_same_value_spec, taint_after_write
from pipelex.pipe_machinery.validation import is_valid_input_name
from pipelex.pipe_run.pipe_run_params import BatchParams, PipeRunParams, output_multiplicity_to_apply
from pipelex.system.job_metadata import JobMetadata
from pipelex.validation_error_types import PipeValidationErrorType

if TYPE_CHECKING:
    from pipelex.core.concepts.concept import Concept
    from pipelex.libraries.library_crate import LibraryCrate
    from pipelex.pipe_machinery.pipe_abstract import PipeAbstract


class PipeSequence(PipeController):
    type: Literal["PipeSequence"] = "PipeSequence"
    # The steps in order: pipe steps, which run a pipe, and binding steps, which bind a value already in working memory.
    sequential_sub_pipes: list[SequenceStep]
    # The typed flow and what the sequence stores in its caller's memory, kept for the state of the libraries they were
    # derived in (`SequenceFlowMemo`). An empty memo until the sequence derives them, never `None`: pydantic compares private
    # attributes, and every memo equals every other, so what the sequence derived never changes what it equals.
    _flow_memo: SequenceFlowMemo = PrivateAttr(default_factory=SequenceFlowMemo)

    @override
    def required_variables(self) -> set[str]:
        return set()

    @field_validator("sequential_sub_pipes", mode="after")
    @classmethod
    def validate_sequential_sub_pipes(cls, value: list[SequenceStep]) -> list[SequenceStep]:
        if not value:
            msg = f"PipeSequence '{cls.code}' requires at least one sub-pipe"
            raise ValueError(msg)
        return value

    @override
    def validate_inputs_static(self):
        pass

    @property
    def pipe_steps(self) -> list[SubPipe]:
        """The steps that run a pipe, in order; a binding step runs none."""
        return [step for step in self.sequential_sub_pipes if isinstance(step, SubPipe)]

    def _step_number(self, *, step_index: int) -> int:
        """The number messages give a step: its place among the steps the author wrote, counting from 1."""
        return authored_step_number(steps=self.sequential_sub_pipes, step_index=step_index)

    @property
    def has_binding_step(self) -> bool:
        """Whether a step binds a value, which only a run of a sequence with one reads from the typed flow.

        Every sequence builds its flow, to check each step against it and to say what it stores in its caller's memory
        (`memory_writes`), once per state of the libraries it resolves in (`SequenceFlowMemo`): a run reads the flow kept
        since validation, and a sequence without a binding step never reads it while it runs.
        """
        return any(isinstance(step, BindingStep) for step in self.sequential_sub_pipes)

    def build_typed_flow(self) -> SequenceTypedFlow:
        """The typed flow of the steps, deriving what each binding step binds, built once per state of the current libraries.

        Raises:
            PipeValidationError: ``BINDING_PATH_UNRESOLVED`` when a binding's path cannot be walked.
        """
        return self._build_typed_flow(visited_pipes=set())

    def _build_typed_flow(self, *, visited_pipes: set[str]) -> SequenceTypedFlow:
        """The typed flow, from the memo when a walk that visited none of the pipes the sequence reaches already built it."""
        memo = self._current_flow_memo()
        is_kept = self._is_independent_of_walk(memo=memo, visited_pipes=visited_pipes)
        if is_kept and memo.typed_flow is not None:
            return memo.typed_flow
        typed_flow = build_sequence_typed_flow(
            steps=self.sequential_sub_pipes,
            declared_inputs=self.inputs,
            sequence_code=self.code,
            domain_code=self.domain_code,
            visited_pipes=visited_pipes | {self.visit_key},
        )
        if is_kept:
            memo.typed_flow = typed_flow
        return typed_flow

    def _current_flow_memo(self) -> SequenceFlowMemo:
        """The memo of what this sequence derived from the current pipe and concept libraries, a fresh one once either changed."""
        library_state = (get_pipe_library().state_token, get_concept_library().state_token)
        memo = self._flow_memo
        if not memo.is_valid_for(owner=self, library_state=library_state):
            memo = SequenceFlowMemo(owner=self, library_state=library_state)
            self._flow_memo = memo
        return memo

    def _is_independent_of_walk(self, *, memo: SequenceFlowMemo, visited_pipes: set[str]) -> bool:
        """Whether what the sequence derives inside a walk that visited `visited_pipes` is what it derives in any walk.

        It is unless the walk visited a pipe the sequence reaches, which only a cycle does: the sequence's own walk then
        stops at that pipe, which it would otherwise enter.
        """
        if memo.reachable_visit_keys is None:
            memo.reachable_visit_keys = self._reachable_visit_keys()
        return memo.reachable_visit_keys.isdisjoint(visited_pipes)

    def _reachable_visit_keys(self) -> frozenset[str]:
        """The `visit_key` of every pipe the sequence reaches through its steps' pipes, at any depth, itself excepted."""
        reached_keys: set[str] = {self.visit_key}
        pending_pipes: list[PipeAbstract] = [self]
        while pending_pipes:
            pending_pipe = pending_pipes.pop()
            for dependency_code in pending_pipe.pipe_dependencies():
                dependency = get_optional_pipe(pipe_code=dependency_code)
                if dependency is None or dependency.visit_key in reached_keys:
                    continue
                reached_keys.add(dependency.visit_key)
                pending_pipes.append(dependency)
        return frozenset(reached_keys - {self.visit_key})

    @override
    def memory_writes(self, *, visited_pipes: set[str] | None = None) -> dict[str, MemoryWrite]:
        """What the steps store, as the flow stands after the last one: a sequence runs its steps on its caller's memory.

        Each name the steps store carries the spec the typed flow gives it, the absence the taint walk leaves on it, and
        whether some step stores it on every run. Built once per state of the current libraries, as the typed flow is.

        Raises:
            PipeValidationError: ``BINDING_PATH_UNRESOLVED`` when a binding's path cannot be walked, as validating the
                sequence itself reports.
        """
        if visited_pipes is None:
            visited_pipes = set()
        if self.visit_key in visited_pipes:
            return {}
        memo = self._current_flow_memo()
        is_kept = self._is_independent_of_walk(memo=memo, visited_pipes=visited_pipes)
        if is_kept and memo.memory_writes is not None:
            return dict(memo.memory_writes)
        typed_flow = self._build_typed_flow(visited_pipes=visited_pipes)
        taint_analysis = self._analyze_taint(visited_pipes=visited_pipes | {self.visit_key}, typed_flow=typed_flow)
        written = {
            name: MemoryWrite(
                stuff_spec=slot.stuff_spec,
                disagreement=slot.disagreement,
                absence=taint_analysis.final_slot_taints.get(name),
                is_always_written=name in typed_flow.always_written_names,
            )
            for name, slot in typed_flow.written_slots.items()
        }
        if is_kept:
            memo.memory_writes = written
        return dict(written)

    def _walk_needed_inputs(self, *, visited_pipes: set[str]) -> tuple[InputStuffSpecs, set[str]]:
        """The inputs the steps need from the sequence's caller, and, among them, the roots of binding steps.

        A name is needed when a step reads it before any earlier step stores it on every run: a step stores its result, and
        what its pipe always stores besides (`step_memory_writes`). A name only some runs of an earlier step store, as a
        condition's outcomes that do not all store it, is still needed, since a run may leave it as the caller had it.
        """
        visited_pipes_with_current = visited_pipes | {self.visit_key}
        needed_inputs = InputStuffSpecsFactory.make_empty()
        binding_root_needs: set[str] = set()
        generated_outputs: set[str] = set()

        for sequential_sub_pipe in self.sequential_sub_pipes:
            if isinstance(sequential_sub_pipe, BindingStep):
                # A binding reads its root plainly. A root no earlier step always stores is a needed input of the sequence,
                # typed as the sequence declares it, which is the concept the binding's walk validates its path against. An
                # undeclared root is needed as `Anything`, a flexible need, and refused as a missing input.
                root_name = sequential_sub_pipe.root_name
                if root_name not in generated_outputs:
                    binding_root_needs.add(root_name)
                    if root_name not in needed_inputs.root:
                        declared_root_spec = self.inputs.root.get(root_name)
                        if declared_root_spec is not None:
                            needed_inputs.add_stuff_spec(
                                variable_name=root_name,
                                concept=declared_root_spec.concept,
                                multiplicity=declared_root_spec.multiplicity,
                                presence=declared_root_spec.presence,
                            )
                        else:
                            needed_inputs.add_stuff_spec(
                                variable_name=root_name, concept=get_native_concept(native_concept=NativeConceptCode.ANYTHING)
                            )
                generated_outputs.add(sequential_sub_pipe.output_name)
                continue
            # Skip cross-package pipe refs that aren't loaded yet (dependency not resolved)
            if QualifiedRef.has_cross_package_prefix(sequential_sub_pipe.pipe_code):
                sub_pipe = get_optional_pipe(pipe_code=sequential_sub_pipe.pipe_code)
                if sub_pipe is None:
                    continue
            else:
                sub_pipe = get_required_pipe(pipe_code=sequential_sub_pipe.pipe_code)
            # Use the centralized recursion detection
            sub_pipe_needed_inputs = sub_pipe.needed_inputs(visited_pipes=visited_pipes_with_current)

            if batch_params := sequential_sub_pipe.batch_params:
                try:
                    item_stuff_spec = sub_pipe_needed_inputs.get_required_stuff_spec(variable_name=batch_params.input_item_stuff_name)
                except InputStuffSpecNotFoundError as exc:
                    msg = (
                        f"Batch input item named '{batch_params.input_item_stuff_name}' is not "
                        f"in this PipeSequence '{self.code}' input requirements: {sub_pipe_needed_inputs.format_for_display()}"
                    )
                    raise PipeSequenceValueError(msg) from exc
                # The list is needed only when no earlier step stores it, as the binding of a dotted `batch_over` always does,
                # while the batched pipe's other inputs are needed whichever step stored the list.
                if batch_params.input_list_stuff_name not in generated_outputs:
                    needed_inputs.add_stuff_spec(variable_name=batch_params.input_list_stuff_name, concept=item_stuff_spec.concept, multiplicity=True)
                for input_name, stuff_spec in sub_pipe_needed_inputs.items:
                    if input_name != batch_params.input_item_stuff_name and input_name not in generated_outputs:
                        needed_inputs.add_stuff_spec(
                            variable_name=input_name,
                            concept=stuff_spec.concept,
                            multiplicity=stuff_spec.multiplicity,
                            presence=stuff_spec.presence,
                        )
            else:
                for input_name, stuff_spec in sub_pipe_needed_inputs.items:
                    if input_name not in generated_outputs:
                        needed_inputs.add_stuff_spec(
                            variable_name=input_name, concept=stuff_spec.concept, multiplicity=stuff_spec.multiplicity, presence=stuff_spec.presence
                        )

            # What the step stores on every run, besides its result, and its result.
            step_writes = step_memory_writes(step=sequential_sub_pipe, step_pipe=sub_pipe, visited_pipes=visited_pipes_with_current)
            generated_outputs.update(written_name for written_name, memory_write in step_writes.items() if memory_write.is_always_written)
            if sequential_sub_pipe.output_name:
                generated_outputs.add(sequential_sub_pipe.output_name)

        return needed_inputs, binding_root_needs

    @override
    def refuse_undeclared_needed_input(self, *, variable_name: str) -> None:
        """Refuse a binding's root that the sequence neither declares nor always stores, asking for the concept its path walks.

        A root that is not a plain input name cannot be declared, so the refusal asks for a step storing it instead.
        """
        _, binding_root_needs = self._walk_needed_inputs(visited_pipes=set())
        if variable_name not in binding_root_needs:
            return
        for step in self.sequential_sub_pipes:
            if isinstance(step, BindingStep) and step.root_name == variable_name:
                if is_valid_input_name(variable_name):
                    remedy = (
                        f"Declare '{variable_name}' in the sequence's `inputs`, with the concept whose structure holds the path '{step.from_path}'."
                    )
                else:
                    remedy = (
                        f"'{variable_name}' cannot be an input of the sequence, since an input name is a plain snake_case identifier: "
                        f"store a value under '{variable_name}' in an earlier step, whose `result` names it, or bind from a plain name."
                    )
                msg = (
                    f"In pipe '{self.code}', the {step.label} reads '{variable_name}', which is neither an input of the "
                    f"sequence nor always stored by an earlier step. {remedy}"
                )
                raise PipeValidationError(
                    message=msg,
                    error_type=PipeValidationErrorType.MISSING_INPUT_VARIABLE,
                    domain_code=self.domain_code,
                    pipe_code=self.code,
                    variable_names=[variable_name],
                )

    @override
    def validate_inputs_with_library(self):
        """Check every pipe step against the typed flow: each name its pipe reads must hold the concept and multiplicity it reads.

        The flow derives every binding step on the way. A step asking a sequence ending with a binding for a count of outputs
        is checked against what that binding binds first.
        """
        self._refuse_unhonoured_output_counts()
        typed_flow = self.build_typed_flow()
        for step_index, step in enumerate(self.sequential_sub_pipes):
            if not isinstance(step, SubPipe):
                continue
            refusal = self._step_input_refusal(step_index=step_index, step=step, slots=typed_flow.slots_by_pipe_step.get(step_index, {}))
            if refusal is not None:
                raise refusal

    def _accepted_declared_names(self, *, visited_pipes: set[str]) -> frozenset[str]:
        """The declared inputs whose declared spec every pipe step reading the caller's value under them accepts, as the check
        of each step against the typed flow (`validate_inputs_with_library`) judges it, once per state of the current libraries.

        That check is the authority on whether a declared input fits the steps reading it, so a declaration it accepts is what
        the sequence needs (`needed_inputs`): a first step reading `note` as `Markdown` and a second reading it as `Text` are
        both satisfied by a `Markdown`, which is not the last step's need.

        Raises:
            PipeValidationError: ``BINDING_PATH_UNRESOLVED`` when a binding's path cannot be walked, as validating the sequence
                itself reports.
        """
        memo = self._current_flow_memo()
        is_kept = self._is_independent_of_walk(memo=memo, visited_pipes=visited_pipes)
        if is_kept and memo.accepted_declared_names is not None:
            return memo.accepted_declared_names
        typed_flow = self._build_typed_flow(visited_pipes=visited_pipes)
        refused_names: set[str] = set()
        for step_index, step in enumerate(self.sequential_sub_pipes):
            if not isinstance(step, SubPipe):
                continue
            for variable_name, slot in typed_flow.slots_by_pipe_step.get(step_index, {}).items():
                if variable_name in refused_names or variable_name not in self.inputs.root or slot.producer_step_index is not None:
                    # Already refused, not a declared input, or a value an earlier step stored there rather than the caller's.
                    continue
                if self._step_input_refusal(step_index=step_index, step=step, slots={variable_name: slot}) is not None:
                    refused_names.add(variable_name)
        accepted_names = frozenset(name for name in self.inputs.root if name not in refused_names)
        if is_kept:
            memo.accepted_declared_names = accepted_names
        return accepted_names

    def _step_input_refusal(self, *, step_index: int, step: SubPipe, slots: dict[str, FlowSlot]) -> PipeValidationError | None:
        """The refusal of a pipe step whose pipe declares an input, among the slots given, as a spec the slot does not hold,
        `None` when every one of them holds what the pipe declares.

        A step is checked against the inputs its pipe declares, its contract. An operator needs exactly what it declares. A
        controller's declaration is what its own validation holds its steps, outcomes or branches to, while what it needs
        (`needed_inputs`) keeps one need per name, which for a nested sequence is its declaration only where every step reading
        the name accepts it. Reading the declaration never walks the pipe's own steps, so the sequence's `needed_inputs` can ask
        this check which of its declarations it accepts.

        A slot the flow cannot type, a value a pipe that does not resolve stored, is assumed to deliver, and so is the concept of
        a value a pipe step stored as `Anything` or `Dynamic`. A slot whose possible values have different specs is checked
        against each of them, each read as what stored it. The refusal is returned rather than raised, so that the same check
        answers which declared inputs are accepted (`_accepted_declared_names`).

        Returns:
            ``INPUT_STUFF_SPEC_MISMATCH`` naming the step, the name and what stored it, or `None`.
        """
        step_pipe = get_optional_pipe(pipe_code=step.pipe_code)
        if step_pipe is None:
            return None
        step_contract = step_pipe.inputs
        batch_item_name: str | None = None
        if step.batch_params is not None:
            batch_item_name = step.batch_params.input_item_stuff_name
            list_slot = slots.get(step.batch_params.input_list_stuff_name)
            if list_slot is not None:
                list_refusal = self._batched_list_refusal(
                    step_index=step_index,
                    step_pipe_code=step_pipe.code,
                    batch_params=step.batch_params,
                    slot=list_slot,
                    item_need=step_contract.root.get(batch_item_name),
                )
                if list_refusal is not None:
                    return list_refusal
        for input_name, needed_spec in step_contract.items:
            if input_name == batch_item_name:
                continue
            slot = slots.get(input_name)
            if slot is None:
                continue
            read_refusal = self._slot_read_refusal(
                step_index=step_index, step_pipe_code=step_pipe.code, variable_name=input_name, slot=slot, needed_spec=needed_spec
            )
            if read_refusal is not None:
                return read_refusal
        return None

    def final_binding_spec(self) -> StuffSpec | None:
        """The spec the binding step ending the sequence binds, `None` when the last step runs a pipe or the flow cannot type the binding's root.

        Raises:
            PipeValidationError: ``BINDING_PATH_UNRESOLVED`` when a binding's path cannot be walked, as validating the sequence
                itself reports.
        """
        if not isinstance(self.sequential_sub_pipes[-1], BindingStep):
            return None
        return self.build_typed_flow().binding_specs.get(len(self.sequential_sub_pipes) - 1)

    def _refuse_unhonoured_output_counts(self) -> None:
        """Refuse a step asking, with `nb_output` or `multiple_output`, a sequence ending with a binding for a count its binding
        does not bind.

        A binding binds what its path derives, whatever count its caller asks for, so the request could only reach the called
        sequence's own steps, where a value typed single would hold a list. A batched step runs each branch with the pipe's own
        multiplicity, so its count is never asked of the sequence.

        Raises:
            PipeValidationError: ``INADEQUATE_OUTPUT_MULTIPLICITY`` naming the step and the binding.
        """
        for step_index, step in enumerate(self.sequential_sub_pipes):
            if not isinstance(step, SubPipe) or step.output_multiplicity is None or step.batch_params is not None:
                continue
            step_pipe = get_optional_pipe(pipe_code=step.pipe_code)
            if not isinstance(step_pipe, PipeSequence):
                continue
            bound_spec = step_pipe.final_binding_spec()
            if bound_spec is None:
                continue
            requested = output_multiplicity_to_apply(base_multiplicity=step_pipe.output.multiplicity, override_multiplicity=step.output_multiplicity)
            requested_multiplicity: VariableMultiplicity | None
            if not requested.is_multiple_outputs_enabled:
                requested_multiplicity = None
                requested_label = "a single output"
            elif requested.specific_output_count is not None:
                requested_multiplicity = requested.specific_output_count
                requested_label = f"{requested.specific_output_count} outputs"
            else:
                requested_multiplicity = True
                requested_label = "multiple outputs"
            if is_multiplicity_compatible(source_multiplicity=bound_spec.multiplicity, target_multiplicity=requested_multiplicity):
                continue
            final_binding = step_pipe.sequential_sub_pipes[-1]
            binding_label = final_binding.label if isinstance(final_binding, BindingStep) else "a binding step"
            bound_ref = bound_spec.to_bundle_representation(relative_to_domain=self.domain_code)
            msg = (
                f"In pipe '{self.code}', step {self._step_number(step_index=step_index)} asks pipe '{step_pipe.code}' for {requested_label}, "
                f"but '{step_pipe.code}' "
                f"ends with the {binding_label}, which binds '{bound_ref}': a binding binds what its path derives, whatever "
                f"count its caller asks for. Remove the step's `nb_output` or `multiple_output`, or ask for what the binding binds."
            )
            raise PipeValidationError(
                message=msg,
                error_type=PipeValidationErrorType.INADEQUATE_OUTPUT_MULTIPLICITY,
                domain_code=self.domain_code,
                pipe_code=self.code,
                provided_concept_code=bound_spec.concept.concept_ref,
                required_concept_codes=[step_pipe.output.concept.concept_ref],
            )

    def _render_spec(self, *, stuff_spec: StuffSpec) -> str:
        """A spec's concept and multiplicity as an author writes them in this sequence's domain, its presence aside."""
        return StuffSpec(concept=stuff_spec.concept, multiplicity=stuff_spec.multiplicity).to_bundle_representation(
            relative_to_domain=self.domain_code
        )

    def _producer_label(self, *, producer_step_index: int) -> str:
        """How a message names the pipe step that stored a value, e.g. "step 2 (pipe 'weigh_parcel')"."""
        producer_step = self.sequential_sub_pipes[producer_step_index]
        if isinstance(producer_step, BindingStep):
            return f"the {producer_step.label}"
        producer_pipe = get_optional_pipe(pipe_code=producer_step.pipe_code)
        producer_code = producer_pipe.code if producer_pipe is not None else producer_step.pipe_code
        return f"step {self._step_number(step_index=producer_step_index)} (pipe '{producer_code}')"

    def _slot_read_refusal(
        self, *, step_index: int, step_pipe_code: str, variable_name: str, slot: FlowSlot, needed_spec: StuffSpec
    ) -> PipeValidationError | None:
        """The refusal of a step reading a name as a concept or multiplicity the value the flow carries there does not have,
        `None` when the value satisfies the read.

        A refined concept satisfies its parent, and a fixed count a variable list; a flexible need (`Dynamic`, `Anything`)
        takes any value, and a value a pipe step stored as `Anything` or `Dynamic` has a concept known only when it runs, so
        its concept is assumed to satisfy the read while its multiplicity is still checked. Among the values a disagreement
        lists, only those a pipe step stored are read that way: the value a step may leave in place, when the caller declared it
        or a binding stored it, is checked as any other. The message names what stored the value: a binding step, an earlier
        pipe step, or the sequence's own declared input.

        Returns:
            ``INPUT_STUFF_SPEC_MISMATCH`` naming the step, the name and what stored it, or `None`.
        """
        if needed_spec.concept.code in {NativeConceptCode.DYNAMIC, NativeConceptCode.ANYTHING}:
            return None
        step_label = f"step {self._step_number(step_index=step_index)} (pipe '{step_pipe_code}')"
        needed_ref = self._render_spec(stuff_spec=needed_spec)
        provided_spec = slot.stuff_spec
        if provided_spec is None:
            if slot.disagreement is None:
                # A value a pipe that does not resolve at validation stored: nothing types it, so it is assumed to deliver.
                return None
            # Each value a disagreement lists is read as what stored it: a condition's outcome is a pipe store, while the value
            # the name held before may be the caller's declared input or a binding's, which is checked as any other.
            unreadable_specs = [
                stored_spec.stuff_spec
                for stored_spec in slot.disagreement.stored_specs
                if not self._is_readable_as(
                    provided_spec=stored_spec.stuff_spec, needed_spec=needed_spec, is_stored_by_pipe_step=stored_spec.is_stored_by_pipe_step
                )
            ]
            if not unreadable_specs:
                return None
            msg = (
                f"In pipe '{self.code}', {step_label} reads '{variable_name}' as '{needed_ref}', but the values '{variable_name}' may hold "
                f"have different specs: {slot.disagreement.describe(relative_to_domain=self.domain_code)}. Store '{variable_name}' as a "
                f"'{needed_ref}' wherever it is stored, or declare the input of pipe '{step_pipe_code}' as a concept every one of them satisfies."
            )
            return PipeValidationError(
                message=msg,
                error_type=PipeValidationErrorType.INPUT_STUFF_SPEC_MISMATCH,
                domain_code=self.domain_code,
                pipe_code=self.code,
                variable_names=[variable_name],
                provided_concept_code=unreadable_specs[0].concept.concept_ref,
                required_concept_codes=[needed_spec.concept.concept_ref],
            )
        if self._is_readable_as(provided_spec=provided_spec, needed_spec=needed_spec, is_stored_by_pipe_step=slot.is_stored_by_pipe_step):
            return None
        provided_ref = self._render_spec(stuff_spec=provided_spec)
        declare_remedy = f"Declare the input as '{provided_ref}' in pipe '{step_pipe_code}'"
        if slot.binding_step_index is not None:
            stored_phrase = f"{self._producer_label(producer_step_index=slot.binding_step_index)} binds it"
            remedy = f"{declare_remedy}, or bind a path that reaches a '{needed_ref}'."
        elif slot.producer_step_index is not None:
            producer_label = self._producer_label(producer_step_index=slot.producer_step_index)
            stored_phrase = f"{producer_label} stores it"
            remedy = f"{declare_remedy}, or make {producer_label} store a '{needed_ref}' under '{variable_name}'."
        else:
            stored_phrase = "the sequence declares it"
            remedy = f"{declare_remedy}, or declare '{variable_name}' as '{needed_ref}' in the inputs of pipe '{self.code}'."
        msg = f"In pipe '{self.code}', {step_label} reads '{variable_name}' as '{needed_ref}', but {stored_phrase} as '{provided_ref}'. {remedy}"
        return PipeValidationError(
            message=msg,
            error_type=PipeValidationErrorType.INPUT_STUFF_SPEC_MISMATCH,
            domain_code=self.domain_code,
            pipe_code=self.code,
            variable_names=[variable_name],
            provided_concept_code=provided_spec.concept.concept_ref,
            required_concept_codes=[needed_spec.concept.concept_ref],
        )

    @classmethod
    def _is_readable_as(cls, *, provided_spec: StuffSpec, needed_spec: StuffSpec, is_stored_by_pipe_step: bool) -> bool:
        """Whether a value of `provided_spec` satisfies a read as `needed_spec`: a compatible concept and multiplicity, the
        concept of a value a pipe step stored being assumed to satisfy any read when it is known only when it runs.
        """
        if not is_multiplicity_compatible(source_multiplicity=provided_spec.multiplicity, target_multiplicity=needed_spec.multiplicity):
            return False
        if is_stored_by_pipe_step and cls._is_concept_known_only_at_run(stuff_spec=provided_spec):
            return True
        return get_concept_library().is_compatible(tested_concept=provided_spec.concept, wanted_concept=needed_spec.concept)

    @staticmethod
    def _is_concept_known_only_at_run(*, stuff_spec: StuffSpec) -> bool:
        """Whether a pipe's output spec leaves the concept of the value it stores to the run: `Anything` or `Dynamic`, which a pipe
        declares when what it produces varies, as a condition whose outcomes produce different concepts must declare `Anything`.

        Only a pipe step's store is read this way. The run stores the concept the pipe actually produced, which nothing knows
        before it, so the step reading it is assumed to get what it reads, as from a pipe that does not resolve at validation.
        The sequence's own declared input is a contract its caller is held to, and a binding over a field holding `Anything`
        binds a value whose concept is `Anything`, so both are checked as any other value, also where a later step may leave
        them in place (`FlowSlot.is_stored_by_pipe_step`, `StoredSpec.is_stored_by_pipe_step`). The multiplicity, which the
        pipe's declaration and the step's batch or count set, is checked whatever the concept.
        """
        return stuff_spec.concept.code in {NativeConceptCode.DYNAMIC, NativeConceptCode.ANYTHING}

    def _batched_list_refusal(
        self, *, step_index: int, step_pipe_code: str, batch_params: BatchParams, slot: FlowSlot, item_need: StuffSpec | None
    ) -> PipeValidationError | None:
        """The refusal of a step batching over a value that is not a list, or whose items its pipe reads as another concept,
        `None` when the value is a list of what the pipe reads.

        A dotted `batch_over` is named by the path its author wrote, never by the private name the sequence bound it under.
        A value the flow cannot type is assumed to deliver; one whose possible values have different specs is checked
        against each of them, each read as what stored it. A list a pipe step stored as `Anything[]` or `Dynamic[]` holds
        items whose concept is known only when it runs, so they are assumed to be what the pipe reads, while a single value
        is still no list; a list the caller declared or a binding stored as `Anything[]` is checked as any other.

        Returns:
            ``INPUT_STUFF_SPEC_MISMATCH``, as a batch over a value that is not a list is refused, naming the step and what
            stored the list, or `None`.
        """
        list_name = batch_params.input_list_stuff_name
        item_name = batch_params.input_item_stuff_name
        step_label = f"step {self._step_number(step_index=step_index)} (pipe '{step_pipe_code}')"
        binding_step = self.sequential_sub_pipes[slot.binding_step_index] if slot.binding_step_index is not None else None
        is_bound_list = isinstance(binding_step, BindingStep)
        # Each value the list may be, with whether a pipe step stored it: the slot's own provenance for a typed slot, and each
        # value's for the values a disagreement lists, where the value the name held before may be the caller's or a binding's.
        stored_values: list[tuple[StuffSpec, bool]]
        batched_phrase: str
        list_label = list_name
        if slot.stuff_spec is not None:
            stored_values = [(slot.stuff_spec, slot.is_stored_by_pipe_step)]
            if isinstance(binding_step, BindingStep):
                if binding_step.is_dotted_batch_over:
                    batched_phrase = f"the dotted path '{binding_step.from_path}', which derives"
                    list_label = binding_step.from_path
                else:
                    batched_phrase = f"'{list_name}', which the {binding_step.label} binds as"
            elif slot.producer_step_index is not None:
                batched_phrase = f"'{list_name}', which {self._producer_label(producer_step_index=slot.producer_step_index)} stores as"
            else:
                batched_phrase = f"'{list_name}', which the sequence declares as"
        elif slot.disagreement is not None:
            stored_values = [(stored_spec.stuff_spec, stored_spec.is_stored_by_pipe_step) for stored_spec in slot.disagreement.stored_specs]
            batched_phrase = f"'{list_name}', which may hold"
        else:
            # A list a pipe that does not resolve at validation stored: nothing types it, so it is assumed to deliver.
            return None
        for stored_spec, is_stored_by_pipe_step in stored_values:
            stored_ref = self._render_spec(stuff_spec=stored_spec)
            if not stored_spec.is_multiple():
                list_remedy = "a path that reaches a list, through a list root or a list field" if is_bound_list else "a name holding a list"
                msg = (
                    f"In pipe '{self.code}', {step_label} batches over {batched_phrase} a single '{stored_ref}', not a list: a batch runs its "
                    f"pipe once per item of a list. Batch over {list_remedy}, or run the step on the value itself, without `batch_over`."
                )
                return PipeValidationError(
                    message=msg,
                    error_type=PipeValidationErrorType.INPUT_STUFF_SPEC_MISMATCH,
                    domain_code=self.domain_code,
                    pipe_code=self.code,
                    variable_names=[list_label],
                    provided_concept_code=stored_spec.concept.concept_ref,
                )
            if item_need is None or item_need.concept.code in {NativeConceptCode.DYNAMIC, NativeConceptCode.ANYTHING}:
                continue
            if is_stored_by_pipe_step and self._is_concept_known_only_at_run(stuff_spec=stored_spec):
                continue
            if get_concept_library().is_compatible(tested_concept=stored_spec.concept, wanted_concept=item_need.concept):
                continue
            item_ref = StuffSpec(concept=stored_spec.concept).to_bundle_representation(relative_to_domain=self.domain_code)
            needed_ref = StuffSpec(concept=item_need.concept).to_bundle_representation(relative_to_domain=self.domain_code)
            list_remedy = "a path that reaches a list" if is_bound_list else "a list"
            msg = (
                f"In pipe '{self.code}', {step_label} batches over {batched_phrase} '{stored_ref}', but its pipe reads each item, "
                f"'{item_name}', as '{needed_ref}'. Declare '{item_name}' as '{item_ref}' in pipe '{step_pipe_code}', or batch over "
                f"{list_remedy} of '{needed_ref}'."
            )
            return PipeValidationError(
                message=msg,
                error_type=PipeValidationErrorType.INPUT_STUFF_SPEC_MISMATCH,
                domain_code=self.domain_code,
                pipe_code=self.code,
                variable_names=[item_name],
                provided_concept_code=stored_spec.concept.concept_ref,
                required_concept_codes=[item_need.concept.concept_ref],
            )
        return None

    @override
    def validate_output_static(self):
        pass

    @override
    def validate_output_with_library(self):
        """Validate the output for the pipe sequence.

        The output of the pipe sequence should match the output of the last step, both in terms of concept
        compatibility and multiplicity. A last step that binds a value is checked by the spec it derives, exactly
        as a pipe step is checked by its pipe's output.
        """
        last_step = self.sequential_sub_pipes[-1]
        last_step_concept: Concept
        last_step_label: str
        is_last_step_output_optional: bool
        effective_last_step_output_multiplicity: VariableMultiplicity | None
        if isinstance(last_step, BindingStep):
            typed_flow = self.build_typed_flow()
            binding_spec = typed_flow.binding_specs.get(len(self.sequential_sub_pipes) - 1)
            if binding_spec is None:
                # A root a pipe that does not resolve stored: nothing says what the binding derives, so only its absence is
                # checked here, and the run checks the binding it derives against the output (`_refuse_runtime_output_mismatch`).
                self._refuse_escaping_absence(taint_analysis=self._analyze_taint(visited_pipes=None, typed_flow=typed_flow))
                return
            last_step_concept = binding_spec.concept
            last_step_label = f"the {last_step.label}"
            # A binding's own maybe-absence is the taint pass's to report, as its result's taint.
            is_last_step_output_optional = False
            effective_last_step_output_multiplicity = binding_spec.multiplicity
        else:
            last_step_pipe_code = last_step.pipe_code
            # Skip output validation if the last step is an unresolved cross-package ref
            if QualifiedRef.has_cross_package_prefix(last_step_pipe_code) and get_optional_pipe(pipe_code=last_step_pipe_code) is None:
                return
            last_step_pipe = get_required_pipe(pipe_code=last_step_pipe_code)
            last_step_concept = last_step_pipe.output.concept
            last_step_label = f"'{last_step_pipe.code}'"
            # What the step stores under its result, resolved exactly the way the run path and the typed flow resolve it
            # (`SubPipe.result_spec`): the pipe's declared multiplicity with the step's `nb_output` or `multiple_output`
            # override, or, for a batched step, the variable list of its branches' results, whatever count it asks for.
            last_step_result_spec = last_step.result_spec(step_pipe=last_step_pipe)
            is_last_step_output_optional = last_step_result_spec.presence.is_optional
            effective_last_step_output_multiplicity = last_step_result_spec.multiplicity
        is_plural_last_step_output = is_multiple_multiplicity(multiplicity=effective_last_step_output_multiplicity)

        taint_analysis = self.analyze_taint()

        # The last step's effective output in bundle representation — what the sequence's declared
        # output should be. This is the enriched semantic fact the fix planner needs, rendered the
        # way an author in the sequence's domain would write it, with the resolved multiplicity
        # and boundary presence. A singular sequence boundary remains
        # optional when its declaration, last step, or taint propagation says it may be absent.
        # Plural outputs must stay plain because the grammar forbids combining multiplicity with
        # a presence marker and represents an absent plural result as an empty list.
        expected_output_presence = PresenceMarker.PLAIN
        if not is_plural_last_step_output and (
            self.output.presence.is_optional or is_last_step_output_optional or taint_analysis.output_taint is not None
        ):
            expected_output_presence = PresenceMarker.OPTIONAL
        expected_output_ref = StuffSpec(
            concept=last_step_concept,
            multiplicity=effective_last_step_output_multiplicity,
            presence=expected_output_presence,
        ).to_bundle_representation(relative_to_domain=self.domain_code)

        # Check concept compatibility
        if not get_concept_library().is_compatible(tested_concept=last_step_concept, wanted_concept=self.output.concept):
            msg = (
                f"PipeSequence concept mismatch: the output concept '{last_step_concept.concept_ref}' "
                f"of the last step {last_step_label} of sequence pipe '{self.code}' "
                f"is not compatible with the output concept '{self.output.concept.concept_ref}' of the sequence."
            )
            raise PipeValidationError(
                message=msg,
                error_type=PipeValidationErrorType.INADEQUATE_OUTPUT_CONCEPT,
                domain_code=self.domain_code,
                pipe_code=self.code,
                provided_concept_code=last_step_concept.concept_ref,
                required_concept_codes=[self.output.concept.concept_ref],
                expected_output_ref=expected_output_ref,
            )

        # Check multiplicity compatibility
        if not is_multiplicity_compatible(
            source_multiplicity=effective_last_step_output_multiplicity,
            target_multiplicity=self.output.multiplicity,
        ):
            declared_output_ref = self.output.to_bundle_representation(relative_to_domain=self.domain_code)
            msg = (
                f"PipeSequence output multiplicity mismatch: the sequence '{self.code}' declares its output as "
                f"'{declared_output_ref}', but its last step {last_step_label} yields '{expected_output_ref}'. "
                f"Update the sequence's output to '{expected_output_ref}' (or change the last step)."
            )
            raise PipeValidationError(
                message=msg,
                error_type=PipeValidationErrorType.INADEQUATE_OUTPUT_MULTIPLICITY,
                domain_code=self.domain_code,
                pipe_code=self.code,
                provided_concept_code=last_step_concept.concept_ref,
                required_concept_codes=[self.output.concept.concept_ref],
                expected_output_ref=expected_output_ref,
            )

        self._refuse_escaping_absence(taint_analysis=taint_analysis)

    def _refuse_escaping_absence(self, *, taint_analysis: SequenceTaintAnalysis) -> None:
        """The absence-taint boundary check (D6): a maybe-absent slot ending the sequence must be matched by an optional
        (`?`) declared output, or the taint silently escapes the boundary.
        """
        if taint_analysis.output_taint is not None and not self.output.presence.is_optional:
            msg = (
                f"PipeSequence '{self.code}' output '{self.output.concept.concept_ref}' may resolve absent at run time, "
                f"but the output is not declared optional. {taint_analysis.output_taint.describe()} "
                f"Fix: declare the sequence output optional ('{self.output.concept.concept_ref}?'), absorb the absence "
                f"with an optional input ('X?') on a downstream step and guard its use, or assert presence with a "
                f"force input ('X!')."
            )
            raise PipeValidationError(
                message=msg,
                error_type=PipeValidationErrorType.OPTIONAL_NOT_HANDLED,
                domain_code=self.domain_code,
                pipe_code=self.code,
                provided_concept_code=self.output.concept.concept_ref,
                variable_names=[taint_analysis.output_taint.origin_slot_name],
            )

    def analyze_taint(self) -> SequenceTaintAnalysis:
        """Static absence-taint walk over the steps (D6), computing per-slot presence.

        Taint enters through the sequence's own `?` inputs and through steps producing optional
        outputs; it propagates through lifted steps (plain input fed a tainted slot), terminates
        at `?` (absorb) and `!` (assert) inputs, and never touches plural slots (D4). A step that
        rewrites a tainted slot with a guaranteed value clears it — the static mirror of the
        runtime value-supersedes-record invariant. What a step stores besides its result, a nested
        controller's names (`step_memory_writes`), carries its own absence the same way.
        """
        return self._analyze_taint(visited_pipes=None, typed_flow=None)

    def _analyze_taint(self, *, visited_pipes: set[str] | None, typed_flow: SequenceTypedFlow | None) -> SequenceTaintAnalysis:
        """The taint walk, over a typed flow already built when `typed_flow` is given, whose per-step stores it then reads
        instead of computing them again.

        With `visited_pipes`, the walk runs inside the recursion guard of `memory_writes`, which reads only the absences it
        leaves on the slots: a step is then scanned for its consumptions only while some slot may be absent, since with none
        it lifts on nothing, and only the `!` lint reads what it consumes. That keeps a caller's needed inputs, which read
        `memory_writes` for every nested controller, from walking each nested controller's needs a second time.
        """
        slot_taints: dict[str, SlotTaint] = {}
        for input_name, stuff_spec in self.inputs.root.items():
            if stuff_spec.presence.is_optional and not stuff_spec.is_multiple():
                slot_taints[input_name] = SlotTaint(
                    source=f"optional input '{input_name}' of pipe '{self.code}'",
                    origin_slot_name=input_name,
                )

        liftable_steps: list[LiftableStepInfo] = []
        force_consumptions: list[ForceConsumptionInfo] = []
        last_step_taint: SlotTaint | None = None
        if typed_flow is None and self.has_binding_step:
            typed_flow = self._build_typed_flow(visited_pipes=visited_pipes or set())
        writes_visited_pipes = visited_pipes or {self.visit_key}

        for step_index, sequential_sub_pipe in enumerate(self.sequential_sub_pipes):
            if isinstance(sequential_sub_pipe, BindingStep):
                binding_taint = self._binding_step_taint(
                    binding_step=sequential_sub_pipe,
                    derivation=typed_flow.binding_derivations.get(step_index) if typed_flow is not None else None,
                    root_taint=slot_taints.get(sequential_sub_pipe.root_name),
                )
                if binding_taint is None:
                    slot_taints.pop(sequential_sub_pipe.output_name, None)
                else:
                    slot_taints[sequential_sub_pipe.output_name] = binding_taint
                last_step_taint = binding_taint
                continue
            sub_pipe = get_optional_pipe(pipe_code=sequential_sub_pipe.pipe_code)
            if sub_pipe is None:
                # Unresolved cross-package ref: assume the step delivers (conservative-permissive,
                # mirroring needed_inputs), so a partially-loaded library never false-errors.
                last_step_taint = None
                if sequential_sub_pipe.output_name:
                    slot_taints.pop(sequential_sub_pipe.output_name, None)
                continue

            # How does this step consume the currently tainted slots?
            if visited_pipes is not None and not slot_taints:
                trigger_scan = TaintTriggerScan(trigger_names=(), trigger_taint=None)
            else:
                trigger_scan = scan_taint_triggers(sub_pipe, slot_taints=slot_taints, visited_pipes=visited_pipes)
            for asserting_name in trigger_scan.asserting_force_names:
                force_consumptions.append(
                    ForceConsumptionInfo(within_pipe_ref=self.pipe_ref, pipe_ref=sub_pipe.pipe_ref, variable_name=asserting_name, is_asserting=True)
                )
            for redundant_name in trigger_scan.redundant_force_names:
                force_consumptions.append(
                    ForceConsumptionInfo(within_pipe_ref=self.pipe_ref, pipe_ref=sub_pipe.pipe_ref, variable_name=redundant_name, is_asserting=False)
                )
            trigger_taint = trigger_scan.trigger_taint
            step_lifted = bool(trigger_scan.trigger_names) and trigger_taint is not None
            if step_lifted and trigger_taint is not None:
                liftable_steps.append(
                    LiftableStepInfo(
                        within_pipe_ref=self.pipe_ref,
                        pipe_ref=sub_pipe.pipe_ref,
                        trigger_variable_names=trigger_scan.trigger_names,
                        absence_source=trigger_taint.source,
                    ),
                )

            # The step's own output presence. A plural result is never tainted (D4): a lifted
            # plural output normalizes to an empty list and a batched step compacts.
            output_slot_name = sequential_sub_pipe.output_name
            is_plural_result = is_plural_step_result(
                sub_pipe,
                step_output_multiplicity=sequential_sub_pipe.output_multiplicity,
                has_batch_params=sequential_sub_pipe.batch_params is not None,
            )
            step_output_taint: SlotTaint | None = None
            if not is_plural_result:
                if step_lifted and trigger_taint is not None:
                    step_output_taint = SlotTaint(
                        source=trigger_taint.source,
                        origin_slot_name=trigger_taint.origin_slot_name,
                        chain=(
                            *trigger_taint.chain,
                            f"pipe '{sub_pipe.code}' may be skipped when '{trigger_scan.trigger_names[0]}' is absent"
                            + (f" → slot '{output_slot_name}'" if output_slot_name else ""),
                        ),
                    )
                elif sub_pipe.output.presence.is_optional:
                    step_output_taint = SlotTaint(
                        source=f"optional output of pipe '{sub_pipe.code}'",
                        origin_slot_name=output_slot_name or sub_pipe.code,
                    )

            # What the step stores besides its result: a nested sequence's steps, a condition's outcome, or an
            # add_each_output parallel's branches write into this flow, each name with its own absence.
            if typed_flow is not None and step_index in typed_flow.memory_writes_by_pipe_step:
                step_writes = typed_flow.memory_writes_by_pipe_step[step_index]
            else:
                step_writes = step_memory_writes(step=sequential_sub_pipe, step_pipe=sub_pipe, visited_pipes=writes_visited_pipes)
            for written_name, memory_write in step_writes.items():
                if step_lifted and trigger_taint is not None:
                    # The whole step lifts: what it always stores resolves exactly like the runtime
                    # `_make_lifted_output` resolves its companion slots — a singular slot goes absent,
                    # a plural slot becomes a guaranteed empty list (D4) — and a name only some runs
                    # store is left as it was.
                    if not memory_write.is_always_written:
                        continue
                    if memory_write.stuff_spec is not None and memory_write.stuff_spec.is_multiple():
                        slot_taints.pop(written_name, None)
                    else:
                        slot_taints[written_name] = SlotTaint(
                            source=trigger_taint.source,
                            origin_slot_name=trigger_taint.origin_slot_name,
                            chain=(
                                *trigger_taint.chain,
                                f"pipe '{sub_pipe.code}' may be skipped when '{trigger_scan.trigger_names[0]}' is absent → slot '{written_name}'",
                            ),
                        )
                    continue
                written_taint = taint_after_write(prior_taint=slot_taints.get(written_name), memory_write=memory_write)
                if written_taint is None:
                    slot_taints.pop(written_name, None)
                else:
                    slot_taints[written_name] = written_taint

            if output_slot_name:
                if step_output_taint is None:
                    slot_taints.pop(output_slot_name, None)
                else:
                    slot_taints[output_slot_name] = step_output_taint
            last_step_taint = step_output_taint

        return SequenceTaintAnalysis(
            liftable_steps=tuple(liftable_steps),
            output_taint=last_step_taint,
            force_consumptions=tuple(force_consumptions),
            final_slot_taints=slot_taints,
        )

    @staticmethod
    def _binding_step_taint(
        *,
        binding_step: BindingStep,
        derivation: BindingDerivation | None,
        root_taint: SlotTaint | None,
    ) -> SlotTaint | None:
        """The presence of a binding's result: tainted by its root's taint, or by a path that may find nothing.

        A list result is never tainted, since a lifted binding over a list binds an empty list and a path reaching
        nothing on an item drops it. A root the flow cannot type has no derivation, so whether its path may find nothing,
        or crosses a list, is unknown: the run records a skipped absence when the root is absent (`skip_untyped_root`), so
        the root's own taint is kept, and its path is otherwise assumed to deliver, as an unresolved pipe is.
        """
        if derivation is not None and derivation.is_plural:
            return None
        if root_taint is not None:
            return SlotTaint(
                source=root_taint.source,
                origin_slot_name=root_taint.origin_slot_name,
                chain=(
                    *root_taint.chain,
                    (f"{binding_step.label} may be skipped when '{binding_step.root_name}' is absent → slot '{binding_step.output_name}'"),
                ),
            )
        if derivation is not None and derivation.may_find_nothing:
            return SlotTaint(
                source=f"{binding_step.label}, whose path may find nothing at '{derivation.first_optional_path}'",
                origin_slot_name=binding_step.output_name,
            )
        return None

    @override
    def needed_inputs(self, *, visited_pipes: set[str] | None = None) -> InputStuffSpecs:
        """What the sequence needs from its caller: every name a step reads before an earlier step always stores it.

        The walk of the steps keeps one need per name, the last step's reading it. Where the sequence declares the name and
        every step reading the caller's value under it accepts the declaration (`_accepted_declared_names`), the declaration is
        the need, its concept and multiplicity, so whatever calls the sequence, another sequence, a condition or a parallel, is
        held to what every step accepts rather than to what the last one reads: a sequence declaring `note = "Markdown"` whose
        last step reads a `Text` needs a `Markdown`. A declaration some step refuses leaves the last step's need, which the
        generic check of the inputs then reports with the fix it offers. The presence stays the steps', as every reader of it
        takes the declared marker first.
        """
        if visited_pipes is None:
            visited_pipes = set()

        # If we've already visited this pipe, stop recursion
        if self.visit_key in visited_pipes:
            return InputStuffSpecsFactory.make_empty()

        walked_needs, _ = self._walk_needed_inputs(visited_pipes=visited_pipes)
        differing_names = [
            input_name
            for input_name, walked_spec in walked_needs.items
            if input_name in self.inputs.root and not is_same_value_spec(first_spec=self.inputs.root[input_name], second_spec=walked_spec)
        ]
        if not differing_names:
            return walked_needs
        accepted_names = self._accepted_declared_names(visited_pipes=visited_pipes)
        for input_name in differing_names:
            if input_name not in accepted_names:
                continue
            declared_spec = self.inputs.root[input_name]
            walked_needs.add_stuff_spec(
                variable_name=input_name,
                concept=declared_spec.concept,
                multiplicity=declared_spec.multiplicity,
                presence=walked_needs.root[input_name].presence,
            )
        return walked_needs

    @override
    def pipe_dependencies(self) -> set[str]:
        return {sub_pipe.pipe_code for sub_pipe in self.pipe_steps}

    @override
    async def _live_run_controller_pipe(
        self,
        *,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: str | None = None,
        library_crate: "LibraryCrate | None" = None,
    ) -> PipeOutput:
        evolving_memory = working_memory
        typed_flow: SequenceTypedFlow | None = None
        # By step index, each binding the run derived from the value its root held, the flow having no spec for that root.
        runtime_bindings: dict[int, DerivedBinding] = {}

        for sub_pipe_index, sub_pipe in enumerate(self.sequential_sub_pipes):
            is_last_step = sub_pipe_index == len(self.sequential_sub_pipes) - 1
            if isinstance(sub_pipe, BindingStep):
                if typed_flow is None:
                    typed_flow = self.build_typed_flow()
                self._run_binding_step(
                    binding_step=sub_pipe,
                    step_index=sub_pipe_index,
                    typed_flow=typed_flow,
                    runtime_bindings=runtime_bindings,
                    working_memory=evolving_memory,
                    job_metadata=job_metadata,
                    pipe_run_params=pipe_run_params,
                    is_last_step=is_last_step,
                )
                continue
            if runtime_bindings and typed_flow is not None:
                self._refuse_runtime_consumer_mismatch(
                    step_index=sub_pipe_index, step=sub_pipe, typed_flow=typed_flow, runtime_bindings=runtime_bindings
                )
            # Only the last step should apply the final_stuff_code
            if is_last_step:
                sub_pipe_run_params = pipe_run_params.model_copy()
            else:
                sub_pipe_run_params = pipe_run_params.model_copy(update=({"final_stuff_code": None}))
            pipe_output = await sub_pipe.run_pipe(
                calling_pipe_code=self.code,
                working_memory=evolving_memory,
                job_metadata=job_metadata,
                sub_pipe_run_params=sub_pipe_run_params,
                library_crate=library_crate,
            )
            evolving_memory = pipe_output.working_memory
        # Capture execution data for the graph tracer
        execution_data_dict: dict[str, Any] = {
            "step_count": len(self.sequential_sub_pipes),
        }
        self._register_execution_data(job_metadata=job_metadata, execution_data=execution_data_dict)

        return PipeOutput(
            working_memory=evolving_memory,
            pipeline_run_id=job_metadata.run_metadata.pipeline_run_id,
        )

    def _run_binding_step(
        self,
        *,
        binding_step: BindingStep,
        step_index: int,
        typed_flow: SequenceTypedFlow,
        runtime_bindings: dict[int, DerivedBinding],
        working_memory: WorkingMemory,
        job_metadata: JobMetadata,
        pipe_run_params: PipeRunParams,
        is_last_step: bool,
    ) -> None:
        """Bind one value into the working memory, as a node of the execution graph producing the stuff it binds.

        A binding whose root the flow cannot type, a value a pipe that did not resolve at validation stored, is derived from
        the value the run holds under it, recorded in `runtime_bindings`, and checked against the sequence's output when it
        ends the sequence; it is skipped when the root holds a recorded absence.

        Raises:
            BindingStepRunError: When the path cannot be walked from the concept of the value the root holds, or when the
                binding derived from it ends the sequence and contradicts its declared output.
        """
        derived_binding = self._derived_binding(
            binding_step=binding_step, step_index=step_index, typed_flow=typed_flow, working_memory=working_memory
        )
        if derived_binding is not None and step_index not in typed_flow.binding_specs:
            runtime_bindings[step_index] = derived_binding
            if is_last_step:
                self._refuse_runtime_output_mismatch(binding_step=binding_step, derived_binding=derived_binding)
        node_id = binding_step.trace_start(job_metadata=job_metadata, working_memory=working_memory, domain_code=self.domain_code)
        outcome: BindingOutcome | None = None
        try:
            step_outcome = (
                binding_step.skip_untyped_root(working_memory=working_memory, calling_pipe_code=self.code, run_mode=pipe_run_params.run_mode)
                if derived_binding is None
                else binding_step.bind(
                    working_memory=working_memory,
                    derivation=derived_binding.derivation,
                    result_concept=derived_binding.stuff_spec.concept,
                    calling_pipe_code=self.code,
                    run_mode=pipe_run_params.run_mode,
                    stuff_code=pipe_run_params.final_stuff_code if is_last_step else None,
                )
            )
            outcome = step_outcome
            binding_step.trace_end(job_metadata=job_metadata, node_id=node_id, outcome=step_outcome)
        finally:
            # The node is closed on the way out whatever stopped the binding, a content failing its own validation or a
            # cancellation included, so no binding node is left running. The step returned nothing only if it raised, and
            # the error it raised is the one propagating.
            if outcome is None:
                binding_step.trace_error(job_metadata=job_metadata, node_id=node_id, error=sys.exc_info()[1])

    def _derived_binding(
        self, *, binding_step: BindingStep, step_index: int, typed_flow: SequenceTypedFlow, working_memory: WorkingMemory
    ) -> DerivedBinding | None:
        """What the binding binds: from the flow, or from the value the run holds when the flow cannot type the root, `None`
        when the root holds no value either.
        """
        derivation = typed_flow.binding_derivations.get(step_index)
        binding_spec = typed_flow.binding_specs.get(step_index)
        if derivation is not None and binding_spec is not None:
            return DerivedBinding(derivation=derivation, stuff_spec=binding_spec)
        root_stuff = working_memory.get_optional_stuff(binding_step.root_name)
        if root_stuff is None:
            return None
        return self._derive_from_held_value(binding_step=binding_step, root_stuff=root_stuff)

    def _derive_from_held_value(self, *, binding_step: BindingStep, root_stuff: Stuff) -> DerivedBinding:
        """Derive a binding whose root the flow cannot type from the concept and the shape of the value the root holds.

        Raises:
            BindingStepRunError: When the path cannot be walked from that concept.
        """
        root_multiplicity: VariableMultiplicity | None = True if isinstance(root_stuff.content, ListContent) else None
        try:
            return derive_binding_spec(
                binding_step=binding_step,
                root_spec=StuffSpec(concept=root_stuff.concept, multiplicity=root_multiplicity),
                sequence_code=self.code,
                domain_code=self.domain_code,
            )
        except PipeValidationError as exc:
            msg = (
                f"{exc} The sequence's flow could not type '{binding_step.root_name}', which a pipe that did not resolve at "
                f"validation stores, so the binding was derived from the '{root_stuff.concept.concept_ref}' it holds."
            )
            raise BindingStepRunError(msg) from exc

    def _refuse_runtime_output_mismatch(self, *, binding_step: BindingStep, derived_binding: DerivedBinding) -> None:
        """Refuse a binding ending the sequence, derived when it ran, that contradicts the sequence's declared output, as
        validation refuses one it derives: its concept, its multiplicity, and a result that may be absent behind a plain output.

        Raises:
            BindingStepRunError: Naming the binding, what it binds and the declared output.
        """
        bound_spec = derived_binding.stuff_spec
        is_concept_ok = get_concept_library().is_compatible(tested_concept=bound_spec.concept, wanted_concept=self.output.concept)
        is_multiplicity_ok = is_multiplicity_compatible(source_multiplicity=bound_spec.multiplicity, target_multiplicity=self.output.multiplicity)
        is_presence_ok = not derived_binding.derivation.may_find_nothing or self.output.presence.is_optional
        if is_concept_ok and is_multiplicity_ok and is_presence_ok:
            return
        bound_ref = StuffSpec(
            concept=bound_spec.concept,
            multiplicity=bound_spec.multiplicity,
            presence=PresenceMarker.OPTIONAL if derived_binding.derivation.may_find_nothing else PresenceMarker.PLAIN,
        ).to_bundle_representation(relative_to_domain=self.domain_code)
        declared_ref = self.output.to_bundle_representation(relative_to_domain=self.domain_code)
        msg = (
            f"In pipe '{self.code}', the {binding_step.label} ends the sequence, whose output is declared "
            f"'{declared_ref}', but it binds '{bound_ref}'. A pipe that did not resolve at validation stored '{binding_step.root_name}', "
            "so the binding was derived when it ran, from the value it found. Declare the sequence's output as what the binding binds, "
            "or bind a path that reaches the declared output."
        )
        raise BindingStepRunError(msg)

    def _refuse_runtime_consumer_mismatch(
        self, *, step_index: int, step: SubPipe, typed_flow: SequenceTypedFlow, runtime_bindings: dict[int, DerivedBinding]
    ) -> None:
        """Refuse a pipe step reading the result of a binding derived when it ran as a spec its pipe does not need, as
        validation refuses one reading a binding it derives.

        Raises:
            BindingStepRunError: Naming the step, the binding and both specs.
        """
        runtime_slots: dict[str, FlowSlot] = {}
        for name, slot in typed_flow.slots_by_pipe_step.get(step_index, {}).items():
            if slot.binding_step_index is None or slot.binding_step_index not in runtime_bindings:
                continue
            runtime_spec = runtime_bindings[slot.binding_step_index].stuff_spec
            runtime_slots[name] = FlowSlot(
                stuff_spec=runtime_spec, binding_step_index=slot.binding_step_index, producer_step_index=slot.binding_step_index
            )
        if not runtime_slots:
            return
        refusal = self._step_input_refusal(step_index=step_index, step=step, slots=runtime_slots)
        if refusal is None:
            return
        msg = (
            f"{refusal} The binding was derived when it ran, from the value its root held, since a pipe that did not resolve at "
            "validation stored the root."
        )
        raise BindingStepRunError(msg) from refusal

    @override
    async def _dry_run_controller_pipe(
        self,
        *,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: str | None = None,
        library_crate: "LibraryCrate | None" = None,
    ) -> PipeOutput:
        return await self._live_run_controller_pipe(
            job_metadata=job_metadata,
            working_memory=working_memory,
            pipe_run_params=pipe_run_params,
            output_name=output_name,
            library_crate=library_crate,
        )

    @override
    async def _validate_before_run(
        self, *, job_metadata: JobMetadata, working_memory: WorkingMemory, pipe_run_params: PipeRunParams, output_name: str | None = None
    ):
        pass

    @override
    async def _validate_after_run(
        self, *, job_metadata: JobMetadata, working_memory: WorkingMemory, pipe_run_params: PipeRunParams, output_name: str | None = None
    ):
        pass
