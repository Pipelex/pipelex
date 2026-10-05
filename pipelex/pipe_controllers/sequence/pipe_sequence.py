import sys
from typing import TYPE_CHECKING, Any, Literal

from pydantic import field_validator
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
from pipelex.interpreter_hub import get_concept_library, get_native_concept, get_optional_pipe, get_required_pipe
from pipelex.pipe_controllers.absence_taint import (
    ForceConsumptionInfo,
    LiftableStepInfo,
    SequenceTaintAnalysis,
    SlotTaint,
    is_plural_step_result,
    scan_taint_triggers,
)
from pipelex.pipe_controllers.binding.binding_derivation import BindingDerivation
from pipelex.pipe_controllers.binding.binding_step import BindingOutcome, BindingStep
from pipelex.pipe_controllers.binding.exceptions import BindingStepRunError
from pipelex.pipe_controllers.parallel.pipe_parallel import PipeParallel
from pipelex.pipe_controllers.pipe_controller import PipeController
from pipelex.pipe_controllers.sequence.exceptions import PipeSequenceValueError
from pipelex.pipe_controllers.sequence.sequence_typed_flow import (
    FlowSlot,
    SequenceStep,
    SequenceTypedFlow,
    build_sequence_typed_flow,
)
from pipelex.pipe_controllers.sub_pipe import SubPipe
from pipelex.pipe_run.pipe_run_params import PipeRunParams, output_multiplicity_to_apply
from pipelex.system.job_metadata import JobMetadata
from pipelex.tools.misc.string_utils import get_root_from_dotted_path
from pipelex.validation_error_types import PipeValidationErrorType

if TYPE_CHECKING:
    from pipelex.core.concepts.concept import Concept
    from pipelex.libraries.library_crate import LibraryCrate


class PipeSequence(PipeController):
    type: Literal["PipeSequence"] = "PipeSequence"
    # The steps in order: pipe steps, which run a pipe, and binding steps, which bind a value already in working memory.
    sequential_sub_pipes: list[SequenceStep]

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

    def build_typed_flow(self) -> SequenceTypedFlow:
        """The typed flow of the steps, deriving what each binding step binds.

        Raises:
            PipeValidationError: ``BINDING_PATH_UNRESOLVED`` when a binding's path cannot be walked.
        """
        return build_sequence_typed_flow(
            steps=self.sequential_sub_pipes,
            declared_inputs=self.inputs,
            sequence_code=self.code,
            domain_code=self.domain_code,
        )

    def _binding_root_names(self) -> set[str]:
        """The roots of the binding steps that no earlier step stores, which the sequence must hold as inputs."""
        root_names: set[str] = set()
        stored_names: set[str] = set()
        for step in self.sequential_sub_pipes:
            if isinstance(step, BindingStep) and step.root_name not in stored_names:
                root_names.add(step.root_name)
            if step.output_name:
                stored_names.add(step.output_name)
        return root_names

    @override
    def refuse_undeclared_needed_input(self, *, variable_name: str) -> None:
        """Refuse a binding's root that the sequence neither declares nor stores, asking for the concept its path walks."""
        for step in self.sequential_sub_pipes:
            if isinstance(step, BindingStep) and step.root_name == variable_name and variable_name in self._binding_root_names():
                msg = (
                    f"In pipe '{self.code}', the binding step {step.as_written} reads '{variable_name}', which is neither an input of the "
                    f"sequence nor stored by an earlier step. Declare '{variable_name}' in the sequence's `inputs`, with the concept whose "
                    f"structure holds the path '{step.from_path}'."
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
        """Derive every binding step through the typed flow, then check the steps reading a binding's result against it."""
        typed_flow = self.build_typed_flow()
        for step_index, step in enumerate(self.sequential_sub_pipes):
            if not isinstance(step, SubPipe):
                continue
            binding_slots = typed_flow.binding_slots_by_pipe_step.get(step_index)
            if not binding_slots:
                continue
            step_pipe = get_optional_pipe(pipe_code=step.pipe_code)
            if step_pipe is None:
                continue
            step_needs = step_pipe.needed_inputs()
            batch_item_name: str | None = None
            if step.batch_params is not None:
                batch_item_name = step.batch_params.input_item_stuff_name
                list_slot = binding_slots.get(step.batch_params.input_list_stuff_name)
                item_need = step_needs.root.get(batch_item_name)
                if list_slot is not None and list_slot.stuff_spec is not None and item_need is not None:
                    self._check_binding_consumer(
                        step_index=step_index,
                        step_pipe_code=step_pipe.code,
                        variable_name=step.batch_params.input_list_stuff_name,
                        slot=list_slot,
                        needed_spec=StuffSpec(concept=item_need.concept, multiplicity=True),
                    )
            for input_name, needed_spec in step_needs.items:
                if input_name == batch_item_name:
                    continue
                slot = binding_slots.get(input_name)
                if slot is None or slot.stuff_spec is None:
                    continue
                self._check_binding_consumer(
                    step_index=step_index, step_pipe_code=step_pipe.code, variable_name=input_name, slot=slot, needed_spec=needed_spec
                )

    def _check_binding_consumer(self, *, step_index: int, step_pipe_code: str, variable_name: str, slot: FlowSlot, needed_spec: StuffSpec) -> None:
        """Refuse a step reading a binding's result as a concept or multiplicity the binding does not derive."""
        bound_spec = slot.stuff_spec
        if bound_spec is None or slot.binding_step_index is None:
            return
        if needed_spec.concept.code in {NativeConceptCode.DYNAMIC, NativeConceptCode.ANYTHING}:
            return
        binding_step = self.sequential_sub_pipes[slot.binding_step_index]
        binding_label = binding_step.as_written if isinstance(binding_step, BindingStep) else f"step {slot.binding_step_index + 1}"
        is_concept_compatible = get_concept_library().is_compatible(tested_concept=bound_spec.concept, wanted_concept=needed_spec.concept)
        is_multiplicity_ok = is_multiplicity_compatible(source_multiplicity=bound_spec.multiplicity, target_multiplicity=needed_spec.multiplicity)
        if is_concept_compatible and is_multiplicity_ok:
            return
        bound_ref = StuffSpec(concept=bound_spec.concept, multiplicity=bound_spec.multiplicity).to_bundle_representation(
            relative_to_domain=self.domain_code
        )
        needed_ref = StuffSpec(concept=needed_spec.concept, multiplicity=needed_spec.multiplicity).to_bundle_representation(
            relative_to_domain=self.domain_code
        )
        msg = (
            f"In pipe '{self.code}', step {step_index + 1} (pipe '{step_pipe_code}') reads '{variable_name}' as '{needed_ref}', but the binding "
            f"step {binding_label} binds it as '{bound_ref}'. Declare the input as '{bound_ref}' in pipe '{step_pipe_code}', or bind a path "
            f"that reaches a '{needed_ref}'."
        )
        raise PipeValidationError(
            message=msg,
            error_type=PipeValidationErrorType.INPUT_STUFF_SPEC_MISMATCH,
            domain_code=self.domain_code,
            pipe_code=self.code,
            variable_names=[variable_name],
            provided_concept_code=bound_spec.concept.concept_ref,
            required_concept_codes=[needed_spec.concept.concept_ref],
        )

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
                # A root the flow cannot type, from a pipe that does not resolve: assume it delivers.
                return
            last_step_concept = binding_spec.concept
            last_step_label = f"the binding step {last_step.as_written}"
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
            is_last_step_output_optional = last_step_pipe.output.presence.is_optional

            # The step's effective output, resolved exactly the way the run path resolves it (declared
            # multiplicity + the step-level override), so this static promise cannot rule a count
            # differently from the execution it describes. Reading the two apart — an override tested for
            # truthiness, a declaration tested for `is None` — is what let a `nb_output = 1` step read as
            # plural here while the runtime made it single.
            multiplicity_resolution = output_multiplicity_to_apply(
                base_multiplicity=last_step_pipe.output.multiplicity,
                override_multiplicity=last_step.output_multiplicity,
            )
            # A declaration spells a singular slot with no suffix at all; `resolved_multiplicity` spells a
            # forced single as `False`, which is override vocabulary and renders as nothing an author writes.
            if not multiplicity_resolution.is_multiple_outputs_enabled:
                effective_last_step_output_multiplicity = None
            elif multiplicity_resolution.specific_output_count is not None:
                effective_last_step_output_multiplicity = multiplicity_resolution.specific_output_count
            else:
                effective_last_step_output_multiplicity = True
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

        # The absence-taint boundary check (D6): a maybe-absent slot ending the sequence must be
        # matched by an optional (`?`) declared output, or the taint silently escapes the boundary.
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
        runtime value-supersedes-record invariant.
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
        typed_flow = self.build_typed_flow() if any(isinstance(step, BindingStep) for step in self.sequential_sub_pipes) else None

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
            trigger_scan = scan_taint_triggers(sub_pipe, slot_taints=slot_taints)
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

            # An add_each_output parallel also writes each branch's result slot into this flow.
            if isinstance(sub_pipe, PipeParallel) and sub_pipe.add_each_output:
                if step_lifted and trigger_taint is not None:
                    # The whole parallel lifts: companion (branch) slots resolve exactly like the
                    # runtime `_make_lifted_output` does — singular slots go absent, plural slots
                    # become guaranteed empty lists (D4).
                    for companion_slot in sub_pipe.lifted_companion_slots():
                        if companion_slot.is_plural:
                            slot_taints.pop(companion_slot.slot_name, None)
                        else:
                            slot_taints[companion_slot.slot_name] = SlotTaint(
                                source=trigger_taint.source,
                                origin_slot_name=trigger_taint.origin_slot_name,
                                chain=(
                                    *trigger_taint.chain,
                                    (
                                        f"pipe '{sub_pipe.code}' may be skipped when '{trigger_scan.trigger_names[0]}' is absent"
                                        f" → branch slot '{companion_slot.slot_name}'"
                                    ),
                                ),
                            )
                else:
                    branch_taints = sub_pipe.analyze_branch_taint().branch_taints
                    for parallel_sub_pipe in sub_pipe.parallel_sub_pipes:
                        if not parallel_sub_pipe.output_name:
                            continue
                        branch_taint = branch_taints.get(parallel_sub_pipe.output_name)
                        if branch_taint is None:
                            slot_taints.pop(parallel_sub_pipe.output_name, None)
                        else:
                            slot_taints[parallel_sub_pipe.output_name] = branch_taint

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
        nothing on an item drops it. A root the flow cannot type is assumed to deliver, as an unresolved pipe is.
        """
        if derivation is None or derivation.is_plural:
            return None
        if root_taint is not None:
            return SlotTaint(
                source=root_taint.source,
                origin_slot_name=root_taint.origin_slot_name,
                chain=(
                    *root_taint.chain,
                    (
                        f"binding step {binding_step.as_written} may be skipped when '{binding_step.root_name}' is absent"
                        f" → slot '{binding_step.output_name}'"
                    ),
                ),
            )
        if derivation.may_find_nothing:
            return SlotTaint(
                source=f"binding step {binding_step.as_written}, whose path may find nothing at '{derivation.first_optional_path}'",
                origin_slot_name=binding_step.output_name,
            )
        return None

    @override
    def needed_inputs(self, *, visited_pipes: set[str] | None = None) -> InputStuffSpecs:
        if visited_pipes is None:
            visited_pipes = set()

        # If we've already visited this pipe, stop recursion
        if self.visit_key in visited_pipes:
            return InputStuffSpecsFactory.make_empty()

        # Add this pipe to visited set for recursive calls
        visited_pipes_with_current = visited_pipes | {self.visit_key}

        needed_inputs = InputStuffSpecsFactory.make_empty()
        generated_outputs: set[str] = set()

        for sequential_sub_pipe in self.sequential_sub_pipes:
            if isinstance(sequential_sub_pipe, BindingStep):
                # A binding reads its root plainly. A root no earlier step stored is a needed input of the sequence, typed
                # as the sequence declares it, which is the concept the binding's walk validates its path against. An
                # undeclared root is needed as `Anything`, a flexible need, and refused as a missing input.
                root_name = sequential_sub_pipe.root_name
                if root_name not in generated_outputs and root_name not in needed_inputs.root:
                    declared_root_spec = self.inputs.root.get(root_name)
                    if declared_root_spec is not None:
                        needed_inputs.add_stuff_spec(
                            variable_name=root_name,
                            concept=declared_root_spec.concept,
                            multiplicity=declared_root_spec.multiplicity,
                            presence=declared_root_spec.presence,
                        )
                    else:
                        needed_inputs.add_stuff_spec(variable_name=root_name, concept=get_native_concept(native_concept=NativeConceptCode.ANYTHING))
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

            if isinstance(sub_pipe, PipeParallel) and sub_pipe.add_each_output:
                for sub_parallel_pipe in sub_pipe.parallel_sub_pipes:
                    if (sub_pipe.add_each_output and sub_parallel_pipe.output_name) or sub_parallel_pipe.output_name:
                        generated_outputs.add(sub_parallel_pipe.output_name)

            if sequential_sub_pipe.batch_params:
                input_list_root = get_root_from_dotted_path(sequential_sub_pipe.batch_params.input_list_stuff_name)
                if input_list_root not in generated_outputs:
                    try:
                        stuff_spec = sub_pipe_needed_inputs.get_required_stuff_spec(
                            variable_name=sequential_sub_pipe.batch_params.input_item_stuff_name
                        )
                    except InputStuffSpecNotFoundError as exc:
                        msg = (
                            f"Batch input item named '{sequential_sub_pipe.batch_params.input_item_stuff_name}' is not "
                            f"in this PipeSequence '{self.code}' input requirements: {sub_pipe_needed_inputs.format_for_display()}"
                        )
                        raise PipeSequenceValueError(msg) from exc
                    is_dotted_path = "." in sequential_sub_pipe.batch_params.input_list_stuff_name
                    needed_inputs.add_stuff_spec(
                        variable_name=input_list_root,
                        concept=stuff_spec.concept,
                        multiplicity=True if not is_dotted_path else None,
                    )
                    for input_name, stuff_spec in sub_pipe_needed_inputs.items:
                        if input_name != sequential_sub_pipe.batch_params.input_item_stuff_name and input_name not in generated_outputs:
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

            # Add this step's output to generated outputs
            if sequential_sub_pipe.output_name:
                generated_outputs.add(sequential_sub_pipe.output_name)

        return needed_inputs

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

        for sub_pipe_index, sub_pipe in enumerate(self.sequential_sub_pipes):
            is_last_step = sub_pipe_index == len(self.sequential_sub_pipes) - 1
            if isinstance(sub_pipe, BindingStep):
                if typed_flow is None:
                    typed_flow = self.build_typed_flow()
                self._run_binding_step(
                    binding_step=sub_pipe,
                    step_index=sub_pipe_index,
                    typed_flow=typed_flow,
                    working_memory=evolving_memory,
                    job_metadata=job_metadata,
                    pipe_run_params=pipe_run_params,
                    is_last_step=is_last_step,
                )
                continue
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
        working_memory: WorkingMemory,
        job_metadata: JobMetadata,
        pipe_run_params: PipeRunParams,
        is_last_step: bool,
    ) -> None:
        """Bind one value into the working memory, as a node of the execution graph producing the stuff it binds.

        Raises:
            BindingStepRunError: When the flow cannot derive the binding, which validation rules out.
        """
        derivation = typed_flow.binding_derivations.get(step_index)
        binding_spec = typed_flow.binding_specs.get(step_index)
        if derivation is None or binding_spec is None:
            msg = (
                f"In pipe '{self.code}', the binding step {binding_step.as_written} cannot run: the concept of its root "
                f"'{binding_step.root_name}' is unknown to the sequence, so nothing can be derived for it."
            )
            raise BindingStepRunError(msg)
        node_id = binding_step.trace_start(job_metadata=job_metadata, working_memory=working_memory, domain_code=self.domain_code)
        outcome: BindingOutcome | None = None
        try:
            outcome = binding_step.bind(
                working_memory=working_memory,
                derivation=derivation,
                result_concept=binding_spec.concept,
                calling_pipe_code=self.code,
                run_mode=pipe_run_params.run_mode,
                stuff_code=pipe_run_params.final_stuff_code if is_last_step else None,
            )
        finally:
            # The node is closed on the way out whatever stopped the binding, a content failing its own validation or a
            # cancellation included, so no binding node is left running. `bind` returned nothing only if it raised, and
            # the error it raised is the one propagating.
            if outcome is None:
                binding_step.trace_error(job_metadata=job_metadata, node_id=node_id, error=sys.exc_info()[1])
        binding_step.trace_end(job_metadata=job_metadata, node_id=node_id, outcome=outcome)

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
