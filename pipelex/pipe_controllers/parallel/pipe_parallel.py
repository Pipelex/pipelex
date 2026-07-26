import asyncio
import builtins
from typing import TYPE_CHECKING, Any, Literal

from pydantic import field_validator
from typing_extensions import override

from pipelex import log
from pipelex.core.concepts.concept import Concept
from pipelex.core.concepts.exceptions import ConceptValueError
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.absence import AbsenceRecord
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.pipes.exceptions import PipeValidationError, PipeValidationErrorType
from pipelex.core.pipes.inputs.exceptions import InputStuffSpecNotFoundError
from pipelex.core.pipes.inputs.input_stuff_specs import InputStuffSpecs
from pipelex.core.pipes.inputs.input_stuff_specs_factory import InputStuffSpecsFactory
from pipelex.core.pipes.pipe_abstract import CompanionSlot
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.core.stuffs.composite_content import CompositeContent
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.graph.graph_tracer_manager import GraphTracerManager
from pipelex.graph.graphspec import IOSpec
from pipelex.libraries.pipe.exceptions import PipeNotFoundError
from pipelex.method_hub import get_optional_pipe, get_required_pipe
from pipelex.pipe_controllers.absence_taint import (
    ForceConsumptionInfo,
    LiftableStepInfo,
    ParallelTaintAnalysis,
    SlotTaint,
    is_plural_step_result,
    scan_taint_triggers,
)
from pipelex.pipe_controllers.pipe_controller import PipeController
from pipelex.pipe_controllers.sub_pipe import SubPipe
from pipelex.pipe_run.exceptions import PipeRunError
from pipelex.pipe_run.pipe_run_params import PipeRunParams
from pipelex.system.job_metadata import JobMetadata
from pipelex.tools.misc.string_utils import get_root_from_dotted_path

if TYPE_CHECKING:
    from collections.abc import Coroutine

    from pipelex.core.stuffs.stuff import Stuff
    from pipelex.libraries.library_crate import LibraryCrate


class PipeParallel(PipeController):
    type: Literal["PipeParallel"] = "PipeParallel"

    parallel_sub_pipes: list[SubPipe]
    add_each_output: bool

    @field_validator("parallel_sub_pipes", mode="before")
    @classmethod
    def validate_parallel_sub_pipes(cls, parallel_sub_pipes: list[SubPipe]) -> list[SubPipe]:
        seen_output_names: set[str] = set()
        for sub_pipe in parallel_sub_pipes:
            if not sub_pipe.output_name:
                msg = f"PipeParallel '{cls.code}' sub-pipe '{sub_pipe.pipe_code}' output name not specified"
                raise ValueError(msg)
            if sub_pipe.output_name in seen_output_names:
                msg = (
                    f"PipeParallel '{cls.code}' sub-pipe '{sub_pipe.pipe_code}' output name '{sub_pipe.output_name}' "
                    "is already used by another sub-pipe"
                )
                raise ValueError(msg)
            seen_output_names.add(sub_pipe.output_name)
        return parallel_sub_pipes

    @override
    def required_variables(self) -> set[str]:
        return set()

    @override
    def needed_inputs(self, *, visited_pipes: set[str] | None = None) -> InputStuffSpecs:
        if visited_pipes is None:
            visited_pipes = set()

        # If we've already visited this pipe, stop recursion
        if self.pipe_ref in visited_pipes:
            return InputStuffSpecsFactory.make_empty()

        # Add this pipe to visited set for recursive calls
        visited_pipes_with_current = visited_pipes | {self.pipe_ref}

        needed_inputs = InputStuffSpecsFactory.make_empty()

        for sub_pipe in self.parallel_sub_pipes:
            pipe = get_required_pipe(pipe_code=sub_pipe.pipe_code)
            # Use the centralized recursion detection
            pipe_needed_inputs = pipe.needed_inputs(visited_pipes=visited_pipes_with_current)
            if sub_pipe.batch_params:
                try:
                    stuff_spec = pipe_needed_inputs.get_required_stuff_spec(variable_name=sub_pipe.batch_params.input_item_stuff_name)
                except InputStuffSpecNotFoundError as exc:
                    msg = (
                        f"Batch input item named '{sub_pipe.batch_params.input_item_stuff_name}' is not "
                        f"in this Parallel Pipe '{self.code}' input requirements: {pipe_needed_inputs}"
                    )
                    raise PipeValidationError(message=msg) from exc
                input_list_root = get_root_from_dotted_path(sub_pipe.batch_params.input_list_stuff_name)
                needed_inputs.add_stuff_spec(
                    variable_name=input_list_root,
                    concept=stuff_spec.concept,
                    multiplicity=True,
                )
                for input_name, stuff_spec in pipe_needed_inputs.items:
                    if input_name != sub_pipe.batch_params.input_item_stuff_name:
                        needed_inputs.add_stuff_spec(
                            variable_name=input_name, concept=stuff_spec.concept, multiplicity=stuff_spec.multiplicity, presence=stuff_spec.presence
                        )
            else:
                for input_name, stuff_spec in pipe_needed_inputs.items:
                    needed_inputs.add_stuff_spec(
                        variable_name=input_name, concept=stuff_spec.concept, multiplicity=stuff_spec.multiplicity, presence=stuff_spec.presence
                    )
        return needed_inputs

    @override
    def validate_inputs_static(self):
        pass

    @override
    def validate_inputs_with_library(self):
        pass

    @override
    def validate_output_static(self):
        if self.output.multiplicity is not None:
            msg = (
                f"PipeParallel '{self.code}' output must not declare a multiplicity: "
                "a parallel combination is a named composite, never a list (a list aggregation is PipeBatch's shape)."
            )
            raise PipeValidationError(
                message=msg,
                error_type=PipeValidationErrorType.INADEQUATE_OUTPUT_MULTIPLICITY,
                domain_code=self.domain_code,
                pipe_code=self.code,
            )
        output_concept = self.output.concept
        if Concept.is_native_concept(concept=output_concept):
            native_code = NativeConceptCode(output_concept.code)
            if not native_code.is_composite:
                msg = (
                    f"PipeParallel '{self.code}' output '{output_concept.concept_ref}' is invalid: "
                    "the output of a parallel must be 'Composite' or a structured concept whose fields "
                    "correspond to the branch result names."
                )
                raise PipeValidationError(
                    message=msg,
                    error_type=PipeValidationErrorType.INADEQUATE_OUTPUT_CONCEPT,
                    domain_code=self.domain_code,
                    pipe_code=self.code,
                    provided_concept_code=output_concept.concept_ref,
                )

    @override
    def validate_output_with_library(self):
        """Check that the declared output structure can hold the branch results.

        The declared output is either `Composite` (the untyped composition vehicle — accepts any
        branch names) or a structured concept whose fields are compatible with the branch `result`
        names: required fields ⊆ result names, result names ⊆ declared fields. This turns the
        runtime combine failure into an author-time error surfaced by `/validate`.
        """
        try:
            structure_class = self.output.concept.get_structure_class()
        except ConceptValueError as exc:
            # A plain ValueError would escape the /validate sweep and abort the whole bundle;
            # convert it so this pipe alone is reported as failed.
            msg = (
                f"PipeParallel '{self.code}' output '{self.output.concept.concept_ref}' has no registered "
                f"structure class ('{self.output.concept.structure_class_name}'): {exc}"
            )
            raise PipeValidationError(
                message=msg,
                error_type=PipeValidationErrorType.INADEQUATE_OUTPUT_CONCEPT,
                domain_code=self.domain_code,
                pipe_code=self.code,
                provided_concept_code=self.output.concept.concept_ref,
            ) from exc
        if issubclass(structure_class, CompositeContent):
            return

        result_names = {sub_pipe.output_name for sub_pipe in self.parallel_sub_pipes if sub_pipe.output_name}
        declared_fields = set(structure_class.model_fields.keys())
        required_fields = {field_name for field_name, field_info in structure_class.model_fields.items() if field_info.is_required()}

        missing_required_fields = required_fields - result_names
        if missing_required_fields:
            msg = (
                f"PipeParallel '{self.code}' output '{self.output.concept.concept_ref}' requires field(s) "
                f"{sorted(missing_required_fields)} that no branch produces. Branch result names: {sorted(result_names)}. "
                "Each required field of the output structure must match a branch result name."
            )
            raise PipeValidationError(
                message=msg,
                error_type=PipeValidationErrorType.INADEQUATE_OUTPUT_CONCEPT,
                domain_code=self.domain_code,
                pipe_code=self.code,
                provided_concept_code=self.output.concept.concept_ref,
                variable_names=sorted(missing_required_fields),
            )

        extraneous_result_names = result_names - declared_fields
        if extraneous_result_names:
            msg = (
                f"PipeParallel '{self.code}' output '{self.output.concept.concept_ref}' has no field for branch "
                f"result(s) {sorted(extraneous_result_names)}. Declared fields: {sorted(declared_fields)}. "
                "Every branch result name must match a field of the output structure, or use 'Composite' "
                "as the output for an untyped composition."
            )
            raise PipeValidationError(
                message=msg,
                error_type=PipeValidationErrorType.INADEQUATE_OUTPUT_CONCEPT,
                domain_code=self.domain_code,
                pipe_code=self.code,
                provided_concept_code=self.output.concept.concept_ref,
                variable_names=sorted(extraneous_result_names),
            )

        self._validate_branch_output_types(structure_class=structure_class)

        # D11 static rule: a REQUIRED field cannot be fed by a maybe-absent branch — absorption
        # (field-level None) only exists for non-required fields. The runtime guard in
        # `_run_branches_and_combine` is the belt-and-suspenders for this check.
        branch_taints = self.analyze_branch_taint().branch_taints
        for sub_pipe in self.parallel_sub_pipes:
            result_name = sub_pipe.output_name
            if not result_name:
                continue
            branch_taint = branch_taints.get(result_name)
            if branch_taint is None:
                continue
            field_info = structure_class.model_fields.get(result_name)
            if field_info is not None and field_info.is_required():
                msg = (
                    f"PipeParallel '{self.code}': branch '{sub_pipe.pipe_code}' may resolve absent "
                    f"({branch_taint.describe()}), but field '{result_name}' of output "
                    f"'{self.output.concept.concept_ref}' is required. Make the field optional "
                    f"(required = false) or sink the absence upstream (a `?` input on the branch path)."
                )
                raise PipeValidationError(
                    message=msg,
                    error_type=PipeValidationErrorType.OPTIONAL_BRANCH_REQUIRED_FIELD,
                    domain_code=self.domain_code,
                    pipe_code=self.code,
                    provided_concept_code=self.output.concept.concept_ref,
                    variable_names=[result_name],
                )

    def analyze_branch_taint(self) -> ParallelTaintAnalysis:
        """Static taint over the branches (D6): which branch results are maybe-absent.

        Within the parallel's frame, the maybe-absent slots are exactly its own `?`-declared
        inputs (a tainted slot declared plain at the parallel's boundary lifts the whole
        parallel — the enclosing controller's concern, not this walk's). A branch is
        maybe-absent when it is liftable (a plain input fed by an optional input of the
        parallel) or when its pipe declares an optional output; a plural branch result is
        never maybe-absent (D4: compaction / empty list).
        """
        optional_input_taints: dict[str, SlotTaint] = {}
        for input_name, stuff_spec in self.inputs.root.items():
            if stuff_spec.presence.is_optional and not stuff_spec.is_multiple():
                optional_input_taints[input_name] = SlotTaint(
                    source=f"optional input '{input_name}' of pipe '{self.code}'",
                    origin_slot_name=input_name,
                )

        branch_taints: dict[str, SlotTaint] = {}
        liftable_steps: list[LiftableStepInfo] = []
        force_consumptions: list[ForceConsumptionInfo] = []
        for sub_pipe in self.parallel_sub_pipes:
            branch_pipe = get_optional_pipe(pipe_code=sub_pipe.pipe_code)
            if branch_pipe is None:
                continue
            trigger_scan = scan_taint_triggers(branch_pipe, slot_taints=optional_input_taints)
            for asserting_name in trigger_scan.asserting_force_names:
                force_consumptions.append(
                    ForceConsumptionInfo(
                        within_pipe_ref=self.pipe_ref, pipe_ref=branch_pipe.pipe_ref, variable_name=asserting_name, is_asserting=True
                    )
                )
            for redundant_name in trigger_scan.redundant_force_names:
                force_consumptions.append(
                    ForceConsumptionInfo(
                        within_pipe_ref=self.pipe_ref, pipe_ref=branch_pipe.pipe_ref, variable_name=redundant_name, is_asserting=False
                    )
                )
            if trigger_scan.trigger_names and trigger_scan.trigger_taint is not None:
                liftable_steps.append(
                    LiftableStepInfo(
                        within_pipe_ref=self.pipe_ref,
                        pipe_ref=branch_pipe.pipe_ref,
                        trigger_variable_names=trigger_scan.trigger_names,
                        absence_source=trigger_scan.trigger_taint.source,
                    ),
                )
            if not sub_pipe.output_name:
                continue
            if is_plural_step_result(
                branch_pipe, step_output_multiplicity=sub_pipe.output_multiplicity, has_batch_params=sub_pipe.batch_params is not None
            ):
                continue
            if trigger_scan.trigger_names and trigger_scan.trigger_taint is not None:
                branch_taints[sub_pipe.output_name] = SlotTaint(
                    source=trigger_scan.trigger_taint.source,
                    origin_slot_name=trigger_scan.trigger_taint.origin_slot_name,
                    chain=(
                        *trigger_scan.trigger_taint.chain,
                        (
                            f"branch '{branch_pipe.code}' may be skipped when '{trigger_scan.trigger_names[0]}' is absent"
                            f" → result '{sub_pipe.output_name}'"
                        ),
                    ),
                )
            elif branch_pipe.output.presence.is_optional:
                branch_taints[sub_pipe.output_name] = SlotTaint(
                    source=f"optional output of branch pipe '{branch_pipe.code}' (result '{sub_pipe.output_name}')",
                    origin_slot_name=sub_pipe.output_name,
                )
        return ParallelTaintAnalysis(
            branch_taints=branch_taints,
            liftable_steps=tuple(liftable_steps),
            force_consumptions=tuple(force_consumptions),
        )

    @override
    def lifted_companion_slots(self) -> list[CompanionSlot]:
        """When an `add_each_output` parallel is lifted, every branch result slot it would have
        written must be resolved too: a recorded absence for singular results, an empty list for
        plural ones (D4).
        """
        if not self.add_each_output:
            return []
        companion_slots: list[CompanionSlot] = []
        for sub_pipe in self.parallel_sub_pipes:
            if not sub_pipe.output_name:
                continue
            branch_pipe = get_optional_pipe(pipe_code=sub_pipe.pipe_code)
            if branch_pipe is None:
                continue
            companion_slots.append(
                CompanionSlot(
                    slot_name=sub_pipe.output_name,
                    concept=branch_pipe.output.concept,
                    is_plural=is_plural_step_result(
                        branch_pipe,
                        step_output_multiplicity=sub_pipe.output_multiplicity,
                        has_batch_params=sub_pipe.batch_params is not None,
                    ),
                    producing_pipe_code=branch_pipe.code,
                ),
            )
        return companion_slots

    # Note: builtins.type because the `type: Literal["PipeParallel"]` field shadows the
    # builtin in this class body, where signature annotations are evaluated.
    def _validate_branch_output_types(self, *, structure_class: builtins.type[StuffContent]) -> None:
        """Check each branch's output concept against its target field's content class.

        Compatibility is conceptual, not type equality: a branch fits a field when its
        output concept's structure class IS the field's content class or a subclass of
        it — refinement is honored structurally because a refining concept's generated
        class inherits from the refined concept's class (e.g. refines-Text ⇒ subclass
        of TextContent). This is exactly the relation pydantic accepts when
        `StuffFactory.combine_stuffs()` validates the combined content at run time, so
        the check turns that runtime failure into an author-time `/validate` error.

        Conservative by design: fields whose annotation is not a plain StuffContent
        subclass (primitives from .mthds-generated structures, Optionals, unions) and
        list-producing branches are skipped rather than guessed at.
        """
        for sub_pipe in self.parallel_sub_pipes:
            if not sub_pipe.output_name or sub_pipe.output_name not in structure_class.model_fields:
                continue
            field_annotation = structure_class.model_fields[sub_pipe.output_name].annotation
            if not isinstance(field_annotation, type) or not issubclass(field_annotation, StuffContent):
                continue
            branch_pipe = get_required_pipe(pipe_code=sub_pipe.pipe_code)
            if branch_pipe.output.multiplicity is not None:
                # A list-producing branch combines as a ListContent, not as the item class.
                continue
            try:
                branch_structure_class = branch_pipe.output.concept.get_structure_class()
            except ConceptValueError as exc:
                # Same conversion as the output lookup above: keep the failure per-pipe.
                msg = (
                    f"PipeParallel '{self.code}' branch '{sub_pipe.pipe_code}' output "
                    f"'{branch_pipe.output.concept.concept_ref}' has no registered structure class "
                    f"('{branch_pipe.output.concept.structure_class_name}'): {exc}"
                )
                raise PipeValidationError(
                    message=msg,
                    error_type=PipeValidationErrorType.INADEQUATE_OUTPUT_CONCEPT,
                    domain_code=self.domain_code,
                    pipe_code=self.code,
                    provided_concept_code=branch_pipe.output.concept.concept_ref,
                    variable_names=[sub_pipe.output_name],
                ) from exc
            if not issubclass(branch_structure_class, field_annotation):
                msg = (
                    f"PipeParallel '{self.code}' branch '{sub_pipe.pipe_code}' produces "
                    f"'{branch_pipe.output.concept.concept_ref}' (structure '{branch_structure_class.__name__}') for result "
                    f"'{sub_pipe.output_name}', but field '{sub_pipe.output_name}' of output "
                    f"'{self.output.concept.concept_ref}' expects '{field_annotation.__name__}'. "
                    "The branch output concept must match the field's content class or refine a concept that does."
                )
                raise PipeValidationError(
                    message=msg,
                    error_type=PipeValidationErrorType.INADEQUATE_OUTPUT_CONCEPT,
                    domain_code=self.domain_code,
                    pipe_code=self.code,
                    provided_concept_code=branch_pipe.output.concept.concept_ref,
                    variable_names=[sub_pipe.output_name],
                )

    @override
    def pipe_dependencies(self) -> set[str]:
        return {sub_pipe.pipe_code for sub_pipe in self.parallel_sub_pipes}

    async def _run_branches_and_combine(
        self,
        *,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: str | None,
        library_crate: "LibraryCrate | None",
    ) -> PipeOutput:
        """Run all branches on deep copies of the memory, then always combine their outputs.

        Shared by live and dry run: the sub-pipes' own run_pipe dispatch honors the run mode,
        so live and dry runs stamp the same combined main stuff shape.
        """
        # A requested final_stuff_code applies to this pipe's own final output — the COMBINED
        # stuff (e.g. PipeBatch pre-allocates it so its aggregated item identity matches the
        # branch's final output in the graph). Capture it and clear it before fanning out, so the
        # branch runs (which deep-copy the params) don't stamp it on their own outputs.
        final_stuff_code = pipe_run_params.final_stuff_code
        pipe_run_params.final_stuff_code = None

        tasks: list[Coroutine[Any, Any, PipeOutput]] = []

        for sub_pipe in self.parallel_sub_pipes:
            tasks.append(
                sub_pipe.run_pipe(
                    calling_pipe_code=self.code,
                    job_metadata=job_metadata,
                    working_memory=working_memory.make_deep_copy(),
                    sub_pipe_run_params=pipe_run_params.make_deep_copy(),
                    library_crate=library_crate,
                ),
            )

        pipe_outputs = await asyncio.gather(*tasks)

        structure_class = self.output.concept.get_structure_class()
        seen_output_names: set[str] = set()
        output_stuffs: dict[str, Stuff] = {}
        output_stuff_contents: dict[str, StuffContent] = {}

        for output_index, pipe_output in enumerate(pipe_outputs):
            sub_pipe_output_name = self.parallel_sub_pipes[output_index].output_name
            if not sub_pipe_output_name:
                sub_pipe_code = self.parallel_sub_pipes[output_index].pipe_code
                msg = f"PipeParallel '{self.code}': sub-pipe '{sub_pipe_code}' output name not specified"
                raise PipeRunError(message=msg, run_mode=pipe_run_params.run_mode, pipe_code=self.code)
            if sub_pipe_output_name in seen_output_names:
                # TODO: check that at the blueprint / factory level
                sub_pipe_code = self.parallel_sub_pipes[output_index].pipe_code
                msg = f"PipeParallel '{self.code}': sub-pipe '{sub_pipe_code}' duplicate output name '{sub_pipe_output_name}'"
                raise PipeRunError(message=msg, run_mode=pipe_run_params.run_mode, pipe_code=self.code)
            seen_output_names.add(sub_pipe_output_name)
            branch_resolved = pipe_output.working_memory.resolve_main_stuff()
            if isinstance(branch_resolved, AbsenceRecord):
                # Combine under absence (D11): a required structured field cannot be fed a hole —
                # typed error (statically unreachable once Step D's taint pass lands). Otherwise the
                # absent component is omitted from the combine — a non-required structured field
                # absorbs it as field-level None — and a ledger note keeps observability.
                if not issubclass(structure_class, CompositeContent):
                    field_info = structure_class.model_fields.get(sub_pipe_output_name)
                    if field_info is not None and field_info.is_required():
                        sub_pipe_code = self.parallel_sub_pipes[output_index].pipe_code
                        msg = (
                            f"PipeParallel '{self.code}': branch '{sub_pipe_code}' resolved absent "
                            f"({branch_resolved.reason}), but field '{sub_pipe_output_name}' of output "
                            f"'{self.output.concept.concept_ref}' is required. Make the field optional "
                            f"(required = false) or sink the absence upstream (a `?` input on the branch path)."
                        )
                        raise PipeRunError(message=msg, run_mode=pipe_run_params.run_mode, pipe_code=self.code)
                if self.add_each_output:
                    # Branch results are parent slots only under add_each_output — same gate as the
                    # present arm below and as lifted_companion_slots(). Writing the record without
                    # the gate would clobber an unrelated same-named parent value.
                    branch_record = (
                        branch_resolved
                        if branch_resolved.variable_name == sub_pipe_output_name
                        else branch_resolved.model_copy(update={"variable_name": sub_pipe_output_name})
                    )
                    # Resolution, not a note: a stale value under the result name must not outrank it.
                    working_memory.record_resolved_absence(branch_record)
                log.verbose(f"PipeParallel '{self.code}': branch result '{sub_pipe_output_name}' is absent, omitted from the combine")
                continue
            output_stuff = branch_resolved
            if self.add_each_output:
                working_memory.add_new_stuff(name=sub_pipe_output_name, stuff=output_stuff)
            output_stuffs[sub_pipe_output_name] = output_stuff
            output_stuff_contents[sub_pipe_output_name] = output_stuff.content
            log.verbose(f"PipeParallel '{self.code}': output_stuff_contents[{sub_pipe_output_name}]: {output_stuff_contents[sub_pipe_output_name]}")

        # Always combine the branch outputs into the declared output concept and stamp it as main stuff:
        # a pipe run always resolves its declared output — the combine is the parallel's value arm.
        combined_output_stuff = StuffFactory.combine_stuffs(
            concept=self.output.concept,
            stuff_contents=output_stuff_contents,
            name=output_name,
            code=final_stuff_code,
        )
        working_memory.set_new_main_stuff(
            stuff=combined_output_stuff,
            name=output_name,
        )

        # Register parallel combine edges BEFORE register_branch_outputs, because
        # register_parallel_combine snapshots the original branch producers from
        # _stuff_producer_map before register_controller_output overrides them
        self._register_parallel_combine_with_graph_tracer(
            job_metadata=job_metadata,
            combined_stuff=combined_output_stuff,
            branch_stuffs=output_stuffs,
        )

        # Register branch outputs with graph tracer so DATA edges flow from PipeParallel to downstream consumers
        self._register_branch_outputs_with_graph_tracer(
            job_metadata=job_metadata,
            output_stuffs=output_stuffs,
        )

        # Capture execution data for the graph tracer
        execution_data_dict: dict[str, Any] = {
            "branch_count": len(self.parallel_sub_pipes),
            "add_each_output": self.add_each_output,
            "combined_output_concept": self.output.concept.concept_ref,
        }
        self._register_execution_data(job_metadata=job_metadata, execution_data=execution_data_dict)

        return PipeOutput(
            working_memory=working_memory,
            pipeline_run_id=job_metadata.pipeline_run_id,
        )

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
        return await self._run_branches_and_combine(
            job_metadata=job_metadata,
            working_memory=working_memory,
            pipe_run_params=pipe_run_params,
            output_name=output_name,
            library_crate=library_crate,
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
        # Validate that all sub-pipes exist before dispatching the dry branches
        for sub_pipe in self.parallel_sub_pipes:
            try:
                get_required_pipe(pipe_code=sub_pipe.pipe_code)
            except PipeNotFoundError as exc:
                msg = f"Dry run failed for pipe '{self.code}' (PipeParallel): sub-pipe '{sub_pipe.pipe_code}' not found"
                raise PipeRunError(message=msg, run_mode=pipe_run_params.run_mode, pipe_code=self.code) from exc

        return await self._run_branches_and_combine(
            job_metadata=job_metadata,
            working_memory=working_memory,
            pipe_run_params=pipe_run_params,
            output_name=output_name,
            library_crate=library_crate,
        )

    def _register_branch_outputs_with_graph_tracer(
        self,
        *,
        job_metadata: JobMetadata,
        output_stuffs: dict[str, "Stuff"],
    ) -> None:
        """Register branch outputs with the graph tracer.

        This re-registers each branch output's stuff_code as produced by the PipeParallel
        node, overriding the sub-pipe's registration so that DATA edges flow from
        PipeParallel to downstream consumers.

        Args:
            job_metadata: The job metadata containing trace context.
            output_stuffs: Mapping of output_name to the branch output Stuff.
        """
        trace_context = job_metadata.trace_context
        if trace_context is None:
            return
        # E1: in costs-only mode the GraphSpec is never assembled, so skip the controller-output
        # registration entirely — its IOSpec payloads (smart_dump / rendered_pretty_*) would be built
        # then discarded. The node ids minted by on_pipe_start are unaffected.
        if not trace_context.emit_graph_events:
            return
        tracer_manager = GraphTracerManager.get_instance()
        if tracer_manager is None or trace_context.parent_node_id is None:
            return
        for output_name_key, output_stuff in output_stuffs.items():
            output_spec = IOSpec(
                name=output_name_key,
                concept=output_stuff.concept.code,
                content_type=output_stuff.content.content_type,
                digest=output_stuff.stuff_code,
                data=output_stuff.content.smart_dump() if trace_context.data_inclusion.stuff_json_content else None,
                data_text=output_stuff.content.rendered_pretty_text() if trace_context.data_inclusion.stuff_text_content else None,
                data_html=output_stuff.content.rendered_pretty_html() if trace_context.data_inclusion.stuff_html_content else None,
            )
            tracer_manager.register_controller_output(
                lookup_key=trace_context.lookup_key,
                node_id=trace_context.parent_node_id,
                output_spec=output_spec,
            )

    def _register_parallel_combine_with_graph_tracer(
        self,
        *,
        job_metadata: JobMetadata,
        combined_stuff: "Stuff",
        branch_stuffs: dict[str, "Stuff"],
    ) -> None:
        """Register parallel combine edges (branch outputs → combined output).

        Creates PARALLEL_COMBINE edges showing how individual branch results
        are merged into the combined output.

        Args:
            job_metadata: The job metadata containing trace context.
            combined_stuff: The combined output Stuff.
            branch_stuffs: Mapping of output_name to the branch output Stuff.
        """
        trace_context = job_metadata.trace_context
        if trace_context is None:
            return
        tracer_manager = GraphTracerManager.get_instance()
        if tracer_manager is None or trace_context.parent_node_id is None:
            return
        branch_stuff_codes = [stuff.stuff_code for stuff in branch_stuffs.values()]
        tracer_manager.register_parallel_combine(
            lookup_key=trace_context.lookup_key,
            combined_stuff_code=combined_stuff.stuff_code,
            branch_stuff_codes=branch_stuff_codes,
            parallel_controller_node_id=trace_context.parent_node_id,
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
