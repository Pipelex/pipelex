from typing import TYPE_CHECKING, Any, Literal

from pydantic import field_validator
from typing_extensions import override

from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.pipes.exceptions import PipeValidationError, PipeValidationErrorType
from pipelex.core.pipes.inputs.exceptions import InputStuffSpecNotFoundError
from pipelex.core.pipes.inputs.input_stuff_specs import InputStuffSpecs
from pipelex.core.pipes.inputs.input_stuff_specs_factory import InputStuffSpecsFactory
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.core.pipes.stuff_spec.stuff_spec import StuffSpec
from pipelex.core.pipes.variable_multiplicity import is_multiplicity_compatible
from pipelex.core.qualified_ref import QualifiedRef
from pipelex.hub import get_concept_library, get_optional_pipe, get_required_pipe
from pipelex.pipe_controllers.absence_taint import (
    ForceConsumptionInfo,
    LiftableStepInfo,
    SequenceTaintAnalysis,
    SlotTaint,
    is_plural_step_result,
    scan_taint_triggers,
)
from pipelex.pipe_controllers.parallel.pipe_parallel import PipeParallel
from pipelex.pipe_controllers.pipe_controller import PipeController
from pipelex.pipe_controllers.sequence.exceptions import PipeSequenceValueError
from pipelex.pipe_controllers.sub_pipe import SubPipe
from pipelex.pipe_run.pipe_run_params import PipeRunParams
from pipelex.pipeline.job_metadata import JobMetadata
from pipelex.tools.misc.string_utils import get_root_from_dotted_path

if TYPE_CHECKING:
    from pipelex.libraries.library_crate import LibraryCrate


class PipeSequence(PipeController):
    type: Literal["PipeSequence"] = "PipeSequence"
    sequential_sub_pipes: list[SubPipe]

    @override
    def required_variables(self) -> set[str]:
        return set()

    @field_validator("sequential_sub_pipes", mode="after")
    @classmethod
    def validate_sequential_sub_pipes(cls, value: list[SubPipe]) -> list[SubPipe]:
        if not value:
            msg = f"PipeSequence '{cls.code}' requires at least one sub-pipe"
            raise ValueError(msg)
        return value

    @override
    def validate_inputs_static(self):
        pass

    @override
    def validate_inputs_with_library(self):
        pass

    @override
    def validate_output_static(self):
        pass

    @override
    def validate_output_with_library(self):
        """Validate the output for the pipe sequence.

        The output of the pipe sequence should match the output of the last step,
        both in terms of concept compatibility and multiplicity.
        """
        last_sub_pipe = self.sequential_sub_pipes[-1]
        last_step_pipe_code = last_sub_pipe.pipe_code
        # Skip output validation if the last step is an unresolved cross-package ref
        if QualifiedRef.has_cross_package_prefix(last_step_pipe_code) and get_optional_pipe(pipe_code=last_step_pipe_code) is None:
            return
        last_step_pipe = get_required_pipe(pipe_code=last_step_pipe_code)

        effective_last_step_output_multiplicity = last_sub_pipe.output_multiplicity
        if not effective_last_step_output_multiplicity:
            effective_last_step_output_multiplicity = last_step_pipe.output.multiplicity

        # The last step's effective output in bundle representation — what the sequence's declared
        # output should be. This is the enriched semantic fact the fix planner needs, rendered the
        # way an author in the sequence's domain would write it, with the effective multiplicity
        # (sub-pipe override wins) and the presence marker.
        expected_output_ref = StuffSpec(
            concept=last_step_pipe.output.concept,
            multiplicity=effective_last_step_output_multiplicity,
            presence=last_step_pipe.output.presence,
        ).to_bundle_representation(relative_to_domain=self.domain_code)

        # Check concept compatibility
        if not get_concept_library().is_compatible(tested_concept=last_step_pipe.output.concept, wanted_concept=self.output.concept):
            msg = (
                f"PipeSequence concept mismatch: the output concept '{last_step_pipe.output.concept.concept_ref}' "
                f"of the last step '{last_step_pipe.code}' of sequence pipe '{self.code}' "
                f"is not compatible with the output concept '{self.output.concept.concept_ref}' of the sequence."
            )
            raise PipeValidationError(
                message=msg,
                error_type=PipeValidationErrorType.INADEQUATE_OUTPUT_CONCEPT,
                domain_code=self.domain_code,
                pipe_code=self.code,
                provided_concept_code=last_step_pipe.output.concept.concept_ref,
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
                f"'{declared_output_ref}', but its last step '{last_step_pipe.code}' yields '{expected_output_ref}'. "
                f"Update the sequence's output to '{expected_output_ref}' (or change the last step)."
            )
            raise PipeValidationError(
                message=msg,
                error_type=PipeValidationErrorType.INADEQUATE_OUTPUT_MULTIPLICITY,
                domain_code=self.domain_code,
                pipe_code=self.code,
                provided_concept_code=last_step_pipe.output.concept.concept_ref,
                required_concept_codes=[self.output.concept.concept_ref],
                expected_output_ref=expected_output_ref,
            )

        # The absence-taint boundary check (D6): a maybe-absent slot ending the sequence must be
        # matched by an optional (`?`) declared output, or the taint silently escapes the boundary.
        taint_analysis = self.analyze_taint()
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

        for sequential_sub_pipe in self.sequential_sub_pipes:
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

    @override
    def needed_inputs(self, visited_pipes: set[str] | None = None) -> InputStuffSpecs:
        if visited_pipes is None:
            visited_pipes = set()

        # If we've already visited this pipe, stop recursion
        if self.pipe_ref in visited_pipes:
            return InputStuffSpecsFactory.make_empty()

        # Add this pipe to visited set for recursive calls
        visited_pipes_with_current = visited_pipes | {self.pipe_ref}

        needed_inputs = InputStuffSpecsFactory.make_empty()
        generated_outputs: set[str] = set()

        for sequential_sub_pipe in self.sequential_sub_pipes:
            # Skip cross-package pipe refs that aren't loaded yet (dependency not resolved)
            if QualifiedRef.has_cross_package_prefix(sequential_sub_pipe.pipe_code):
                sub_pipe = get_optional_pipe(pipe_code=sequential_sub_pipe.pipe_code)
                if sub_pipe is None:
                    continue
            else:
                sub_pipe = get_required_pipe(pipe_code=sequential_sub_pipe.pipe_code)
            # Use the centralized recursion detection
            sub_pipe_needed_inputs = sub_pipe.needed_inputs(visited_pipes_with_current)

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
                                input_name, concept=stuff_spec.concept, multiplicity=stuff_spec.multiplicity, presence=stuff_spec.presence
                            )
            else:
                for input_name, stuff_spec in sub_pipe_needed_inputs.items:
                    if input_name not in generated_outputs:
                        needed_inputs.add_stuff_spec(
                            input_name, concept=stuff_spec.concept, multiplicity=stuff_spec.multiplicity, presence=stuff_spec.presence
                        )

            # Add this step's output to generated outputs
            if sequential_sub_pipe.output_name:
                generated_outputs.add(sequential_sub_pipe.output_name)

        return needed_inputs

    @override
    def pipe_dependencies(self) -> set[str]:
        return {sub_pipe.pipe_code for sub_pipe in self.sequential_sub_pipes}

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

        for sub_pipe_index, sub_pipe in enumerate(self.sequential_sub_pipes):
            # Only the last step should apply the final_stuff_code
            if sub_pipe_index == len(self.sequential_sub_pipes) - 1:
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
        self._register_execution_data(job_metadata, execution_data=execution_data_dict)

        return PipeOutput(
            working_memory=evolving_memory,
            pipeline_run_id=job_metadata.pipeline_run_id,
        )

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
        self, job_metadata: JobMetadata, *, working_memory: WorkingMemory, pipe_run_params: PipeRunParams, output_name: str | None = None
    ):
        pass

    @override
    async def _validate_after_run(
        self, job_metadata: JobMetadata, *, working_memory: WorkingMemory, pipe_run_params: PipeRunParams, output_name: str | None = None
    ):
        pass
