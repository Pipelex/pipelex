from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict
from typing_extensions import override

from pipelex.cogt.inference.error_classification import UserAction, UserActionKind
from pipelex.cogt.templating.template_rendering import render_template
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.absence import AbsenceKind, AbsenceRecord
from pipelex.core.memory.working_memory import MAIN_STUFF_NAME, WorkingMemory
from pipelex.core.pipes.exceptions import PipeRunError, PipeValidationError
from pipelex.core.pipes.inputs.input_stuff_specs import InputStuffSpecs
from pipelex.core.pipes.inputs.input_stuff_specs_factory import InputStuffSpecsFactory
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.core.stuffs.stuff import Stuff
from pipelex.graph.condition_output_merge import ConditionOutputMerge, ConditionOutputTyping
from pipelex.graph.graph_tracer_manager import GraphTracerManager
from pipelex.interpreter_hub import get_optional_pipe, get_pipe_router, get_required_pipe
from pipelex.pipe_controllers.absence_taint import (
    ConditionTaintAnalysis,
    ForceConsumptionInfo,
    LiftableStepInfo,
    TaintTriggerScan,
    is_plural_step_result,
    optional_input_taints,
    scan_taint_triggers,
)
from pipelex.pipe_controllers.condition.pipe_condition_blueprint import describe_expression_parse_failure
from pipelex.pipe_controllers.condition.special_outcome import SpecialOutcome
from pipelex.pipe_controllers.pipe_controller import PipeController
from pipelex.pipe_machinery.memory_writes import AlternativeWrites, MemoryWrite, SlotTaint, merge_alternative_writes, write_after_lift
from pipelex.pipe_machinery.pipe_abstract import PipeAbstract
from pipelex.pipe_machinery.template_guard_lint import lint_authored_template
from pipelex.pipe_run.pipe_job_factory import PipeJobFactory
from pipelex.pipe_run.pipe_run_params import PipeRunParams, output_multiplicity_to_apply
from pipelex.system.job_metadata import JobMetadata
from pipelex.tools.jinja2.exceptions import Jinja2DetectVariablesError
from pipelex.tools.jinja2.jinja2_required_variables import detect_jinja2_required_variables
from pipelex.tools.jinja2.template_category import TemplateCategory
from pipelex.tools.misc.string_utils import get_root_from_dotted_path
from pipelex.validation_error_types import PipeValidationErrorType

if TYPE_CHECKING:
    from pipelex.libraries.library_crate import LibraryCrate

ConditionOutcomeMap = dict[str, str | SpecialOutcome]


class DryRunOutcomeSlot(BaseModel):
    """What one outcome of a dry-run condition left in the condition's slot, beside what it declares.

    Attributes:
        declared_concept: The concept code the outcome pipe declares as its output.
        declared_list: Whether the outcome pipe declares a list output.
        stuff: The stuff the outcome wrote into the slot, or None where it resolved the slot absent.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    declared_concept: str
    declared_list: bool
    stuff: Stuff | None

    @property
    def declared_typing(self) -> tuple[str, bool]:
        return (self.declared_concept, self.declared_list)

    @property
    def written_typing(self) -> tuple[str, bool] | None:
        if self.stuff is None:
            return None
        return (self.stuff.concept.code, self.stuff.is_list)


class PipeCondition(PipeController):
    type: Literal["PipeCondition"] = "PipeCondition"
    expression: str
    outcome_map: ConditionOutcomeMap
    default_outcome: str | SpecialOutcome
    add_alias_from_expression_to: str | None = None

    @override
    def pipe_dependencies(self) -> set[str]:
        codes = set(self.outcome_map.values())
        if self.default_outcome:
            codes.add(self.default_outcome)
        return codes - set(SpecialOutcome.value_list())

    @override
    def required_variables(self) -> set[str]:
        required_variables: set[str] = set()

        # Variables from the expression/expression_template
        full_paths = detect_jinja2_required_variables(
            template_category=TemplateCategory.EXPRESSION,
            template_source=self.expression,
        )
        required_variables.update(get_root_from_dotted_path(path) for path in full_paths)

        # Variables from the outcomes map and default_outcome
        for pipe_code in self.pipe_dependencies():
            required_variables.update(get_required_pipe(pipe_code=pipe_code).required_variables())

        # Exclude internal variables starting with `_`
        return {var for var in required_variables if not var.startswith("_")}

    @override
    def memory_writes(self, *, visited_pipes: set[str] | None = None) -> dict[str, MemoryWrite]:
        """What the outcome it runs stores besides its result: the chosen outcome runs on the caller's memory.

        The outcomes are merged as alternatives (`merge_alternative_writes`): a name is always written only if every outcome
        that can run stores it, may hold an absence if any outcome may leave one, and keeps a spec only if every outcome
        storing it stores the same one, recording otherwise which outcome stores which spec, so that a binding reading the name
        is refused before the run. An outcome that the condition's own `?` inputs may lift (`analyze_outcome_taint`) may leave
        an absence under every single name it always stores, since its lift resolves them so (`write_after_lift`). A `continue`
        outcome stores nothing, a `fail` outcome stops the run, and an outcome pipe that does not resolve is left out, as a
        sequence assumes an unresolved pipe delivers. The alias the condition may add is left out too: the working memory
        refuses an alias over a name it already holds, so it never replaces a value the flow types.
        """
        if visited_pipes is None:
            visited_pipes = set()
        if self.visit_key in visited_pipes:
            return {}
        visited_pipes_with_current = visited_pipes | {self.visit_key}
        input_taints = optional_input_taints(pipe=self)
        outcome_writes: list[AlternativeWrites] = []
        for outcome_pipe_code in sorted(self.pipe_dependencies()):
            outcome_pipe = get_optional_pipe(pipe_code=outcome_pipe_code)
            if outcome_pipe is None:
                continue
            writes = outcome_pipe.memory_writes(visited_pipes=visited_pipes_with_current)
            if writes and input_taints:
                trigger_scan = scan_taint_triggers(outcome_pipe, slot_taints=input_taints, visited_pipes=visited_pipes_with_current)
                writes = self._writes_after_outcome_lift(outcome_pipe=outcome_pipe, writes=writes, trigger_scan=trigger_scan)
            outcome_writes.append(AlternativeWrites(label=f"outcome '{outcome_pipe.code}' of pipe '{self.code}'", writes=writes))
        if self._continue_reachable:
            outcome_writes.append(AlternativeWrites(label=f"the `continue` outcome of pipe '{self.code}'", writes={}))
        return merge_alternative_writes(alternatives=outcome_writes)

    @classmethod
    def _writes_after_outcome_lift(
        cls, *, outcome_pipe: PipeAbstract, writes: dict[str, MemoryWrite], trigger_scan: TaintTriggerScan
    ) -> dict[str, MemoryWrite]:
        """What an outcome stores, joined with its lift when it consumes plain one of the condition's `?` inputs."""
        trigger_taint = trigger_scan.trigger_taint
        if trigger_taint is None:
            return writes
        return {
            written_name: write_after_lift(
                memory_write=memory_write,
                lift_taint=SlotTaint(
                    source=trigger_taint.source,
                    origin_slot_name=trigger_taint.origin_slot_name,
                    chain=(
                        *trigger_taint.chain,
                        f"pipe '{outcome_pipe.code}' may be skipped when '{trigger_scan.trigger_names[0]}' is absent → slot '{written_name}'",
                    ),
                ),
            )
            for written_name, memory_write in writes.items()
        }

    def analyze_outcome_taint(self, *, visited_pipes: set[str] | None = None) -> ConditionTaintAnalysis:
        """Static taint over the outcomes (D6): which outcome the condition's own `?` inputs may lift.

        Within the condition's frame the maybe-absent slots are exactly its own `?`-declared inputs, as in a parallel's: a
        maybe-absent slot it declares plain lifts the whole condition, which is its caller's concern. An outcome consuming one
        of them plain is lifted when it is chosen with that input absent, which resolves the condition's result, and every
        name the outcome always stores, to an absence, or to an empty list for a list (D4).

        Args:
            visited_pipes: The recursion guard of the walk this one runs inside, handed to each outcome's needed inputs;
                `None` for a walk of its own.
        """
        liftable_steps: list[LiftableStepInfo] = []
        force_consumptions: list[ForceConsumptionInfo] = []
        for outcome_pipe, trigger_scan in self._outcome_trigger_scans(visited_pipes=visited_pipes):
            for asserting_name in trigger_scan.asserting_force_names:
                force_consumptions.append(
                    ForceConsumptionInfo(
                        within_pipe_ref=self.pipe_ref, pipe_ref=outcome_pipe.pipe_ref, variable_name=asserting_name, is_asserting=True
                    )
                )
            for redundant_name in trigger_scan.redundant_force_names:
                force_consumptions.append(
                    ForceConsumptionInfo(
                        within_pipe_ref=self.pipe_ref, pipe_ref=outcome_pipe.pipe_ref, variable_name=redundant_name, is_asserting=False
                    )
                )
            if trigger_scan.trigger_taint is not None:
                liftable_steps.append(
                    LiftableStepInfo(
                        within_pipe_ref=self.pipe_ref,
                        pipe_ref=outcome_pipe.pipe_ref,
                        trigger_variable_names=trigger_scan.trigger_names,
                        absence_source=trigger_scan.trigger_taint.source,
                    )
                )
        return ConditionTaintAnalysis(liftable_steps=tuple(liftable_steps), force_consumptions=tuple(force_consumptions))

    def _outcome_trigger_scans(self, *, visited_pipes: set[str] | None) -> list[tuple[PipeAbstract, TaintTriggerScan]]:
        """How each outcome pipe that resolves consumes the condition's `?` inputs, in the order of the outcome pipe codes."""
        input_taints = optional_input_taints(pipe=self)
        trigger_scans: list[tuple[PipeAbstract, TaintTriggerScan]] = []
        for outcome_pipe_code in sorted(self.pipe_dependencies()):
            outcome_pipe = get_optional_pipe(pipe_code=outcome_pipe_code)
            if outcome_pipe is not None:
                trigger_scans.append((outcome_pipe, scan_taint_triggers(outcome_pipe, slot_taints=input_taints, visited_pipes=visited_pipes)))
        return trigger_scans

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

        # Add the expression variables from self.inputs (with their declared concepts)
        full_paths = detect_jinja2_required_variables(
            template_category=TemplateCategory.EXPRESSION,
            template_source=self.expression,
        )
        expression_variables = {get_root_from_dotted_path(path) for path in full_paths}
        for var_name in expression_variables:
            if not var_name.startswith("_"):
                # Get the concept from declared inputs
                stuff_spec = self.inputs.get_required_stuff_spec(variable_name=var_name)
                needed_inputs.add_stuff_spec(
                    variable_name=var_name,
                    concept=stuff_spec.concept,
                    multiplicity=stuff_spec.multiplicity,
                    presence=stuff_spec.presence,
                )

        # Add the inputs needed by all possible target pipes
        for pipe_code in self.pipe_dependencies():
            pipe = get_required_pipe(pipe_code=pipe_code)
            # Use the centralized recursion detection
            pipe_needed_inputs = pipe.needed_inputs(visited_pipes=visited_pipes_with_current)

            for input_name, stuff_spec in pipe_needed_inputs.items:
                needed_inputs.add_stuff_spec(
                    variable_name=input_name, concept=stuff_spec.concept, multiplicity=stuff_spec.multiplicity, presence=stuff_spec.presence
                )

        return needed_inputs

    @override
    def validate_inputs_static(self):
        # Template lints: no private names, and no declared-optional input referenced unguarded in
        # the expression, which would evaluate over an undefined variable when the value is absent (D7).
        lint_authored_template(
            pipe_code=self.code,
            domain_code=self.domain_code,
            inputs=self.inputs,
            template_source=self.expression,
            template_category=TemplateCategory.EXPRESSION,
            template_label="expression",
        )

    @override
    def validate_inputs_with_library(self):
        pass

    @property
    def _continue_reachable(self) -> bool:
        return SpecialOutcome.is_continue(self.default_outcome) or any(SpecialOutcome.is_continue(outcome) for outcome in self.outcome_map.values())

    @override
    def validate_output_static(self):
        # OPTIONAL_OUTPUT_REQUIRED (D5/D6 of the Optionals design, L-260930-241424): `continue` resolves the declared output as ABSENT,
        # so a `continue`-reachable condition must declare its output optional —
        # otherwise the no-output path would be invisible to the type system, which is exactly
        # the invisible-optional wart this feature removes.
        if self._continue_reachable and not self.output.presence.is_optional:
            msg = (
                f"PipeCondition '{self.code}' can resolve to 'continue', which resolves the declared output as absent, "
                f"but its output '{self.output.concept.concept_ref}' is not declared optional. "
                f"Declare the output optional ('{self.output.concept.concept_ref}?'), or remove the 'continue' outcome."
            )
            raise PipeValidationError(
                message=msg,
                error_type=PipeValidationErrorType.OPTIONAL_OUTPUT_REQUIRED,
                domain_code=self.domain_code,
                pipe_code=self.code,
                provided_concept_code=self.output.concept.concept_ref,
            )

    @override
    def validate_output_with_library(self):
        """Validate the output for the pipe condition.

        Rules:
        1. If all mapped pipes have the same output concept, PipeCondition's output MUST be that same concept.
        2. If mapped pipes have different output concepts, PipeCondition's output MUST be Anything.

        Special outcomes (CONTINUE/FAIL) do not influence the output validation - only actual pipes matter.
        When there are no mapped pipes (all special outcomes), any output is allowed.
        """
        mapped_pipe_codes = self.pipe_dependencies()
        if not mapped_pipe_codes:
            # No actual pipes to validate against (all special outcomes)
            return

        # Boundary taint (D6): a mapped pipe with an optional output makes this condition's own
        # output maybe-absent, so the condition must declare `?` too — otherwise the taint would
        # silently escape through the condition boundary.
        if not self.output.presence.is_optional:
            for pipe_code in sorted(mapped_pipe_codes):
                mapped_pipe = get_required_pipe(pipe_code=pipe_code)
                if mapped_pipe.output.presence.is_optional:
                    msg = (
                        f"PipeCondition '{self.code}' maps outcome pipe '{pipe_code}' whose output "
                        f"'{mapped_pipe.output.concept.concept_ref}' is declared optional, but the condition's own output "
                        f"'{self.output.concept.concept_ref}' is not. Declare the condition's output optional "
                        f"('{self.output.concept.concept_ref}?') so the maybe-absent result stays visible downstream."
                    )
                    raise PipeValidationError(
                        message=msg,
                        error_type=PipeValidationErrorType.OPTIONAL_NOT_HANDLED,
                        domain_code=self.domain_code,
                        pipe_code=self.code,
                        provided_concept_code=self.output.concept.concept_ref,
                    )
            # An outcome that the condition's own `?` inputs may lift resolves the condition's result absent, unless the
            # result is a list, which the lift leaves empty (D4). The expression is not read, so an outcome it chooses only
            # when the input is present is refused too, and forcing the input on that outcome (`!`) is the guarded remedy.
            for outcome_pipe, trigger_scan in self._outcome_trigger_scans(visited_pipes=None):
                if trigger_scan.trigger_taint is None:
                    continue
                if is_plural_step_result(outcome_pipe, step_output_multiplicity=None, has_batch_params=False):
                    continue
                trigger_name = trigger_scan.trigger_names[0]
                msg = (
                    f"PipeCondition '{self.code}' maps outcome pipe '{outcome_pipe.code}', which is skipped when its input "
                    f"'{trigger_name}' is absent, and the condition declares '{trigger_name}' optional, so a run without it "
                    f"resolves the condition's output absent, but that output '{self.output.concept.concept_ref}' is not declared "
                    f"optional. Declare the condition's output optional ('{self.output.concept.concept_ref}?') so the maybe-absent "
                    f"result stays visible downstream, or declare '{trigger_name}' optional on '{outcome_pipe.code}' and handle "
                    f"its absence there. When the condition's expression chooses '{outcome_pipe.code}' only with '{trigger_name}' "
                    f"present, which validation does not read, declare '{trigger_name}' forced on '{outcome_pipe.code}' with '!', "
                    "so that a run reaching it without the input fails instead of resolving the output absent."
                )
                raise PipeValidationError(
                    message=msg,
                    error_type=PipeValidationErrorType.OPTIONAL_NOT_HANDLED,
                    domain_code=self.domain_code,
                    pipe_code=self.code,
                    provided_concept_code=self.output.concept.concept_ref,
                    variable_names=[trigger_name],
                )

        # Collect all unique output concept refs from mapped pipes
        mapped_output_refs: set[str] = set()
        for pipe_code in mapped_pipe_codes:
            pipe = get_required_pipe(pipe_code=pipe_code)
            mapped_output_refs.add(pipe.output.concept.concept_ref)

        all_outputs_same = len(mapped_output_refs) == 1

        if all_outputs_same:
            # All mapped pipes have the same output - PipeCondition MUST use that same output
            expected_output_ref = next(iter(mapped_output_refs))
            if self.output.concept.concept_ref not in {expected_output_ref, NativeConceptCode.ANYTHING.concept_ref}:
                msg = (
                    f"All mapped pipes of PipeCondition '{self.code}' have the same output concept "
                    f"'{expected_output_ref}', but PipeCondition declares output '{self.output.concept.concept_ref}'. "
                    f"When all mapped pipes share the same output, the PipeCondition must use that exact output."
                )
                raise PipeValidationError(
                    message=msg,
                    error_type=PipeValidationErrorType.INADEQUATE_OUTPUT_CONCEPT,
                    domain_code=self.domain_code,
                    pipe_code=self.code,
                    provided_concept_code=self.output.concept.concept_ref,
                    required_concept_codes=[expected_output_ref],
                )
        # Mapped pipes have different outputs - PipeCondition MUST use Dynamic
        elif self.output.concept.concept_ref != NativeConceptCode.ANYTHING.concept_ref:
            msg = (
                f"Mapped pipes of PipeCondition '{self.code}' have different output concepts: "
                f"{sorted(mapped_output_refs)}. When mapped pipes have different outputs, "
                f"the PipeCondition must declare its output as '{NativeConceptCode.ANYTHING.concept_ref}', "
                f"but it declares '{self.output.concept.concept_ref}'."
            )
            raise PipeValidationError(
                message=msg,
                error_type=PipeValidationErrorType.INADEQUATE_OUTPUT_CONCEPT,
                domain_code=self.domain_code,
                pipe_code=self.code,
                provided_concept_code=self.output.concept.concept_ref,
                required_concept_codes=[NativeConceptCode.ANYTHING.concept_ref],
            )

    @override
    async def _validate_before_run(
        self, *, job_metadata: JobMetadata, working_memory: WorkingMemory, pipe_run_params: PipeRunParams, output_name: str | None = None
    ):
        evaluated_expression = await render_template(
            template=self.expression,
            category=TemplateCategory.EXPRESSION,
            context=working_memory.generate_context(),
        )
        if not evaluated_expression or evaluated_expression == "None":
            # The expression is the caller's own method, rendered over their run's data: when it renders
            # nothing, no outcome can be chosen, and the method is theirs to fix. The message names only the pipe.
            error_msg = f"PipeCondition '{self.code}': Conditional expression returned no result"
            raise PipeRunError(
                pipe_code=self.code,
                message=error_msg,
                run_mode=pipe_run_params.run_mode,
            ).as_caller_fault(
                user_action=UserAction(
                    kind=UserActionKind.CHANGE_INPUT,
                    detail=(
                        f"Change the expression of PipeCondition '{self.code}' so that it always renders a value: "
                        "the name of one of its outcomes, or any other value, which takes the default outcome."
                    ),
                )
            )

    @override
    async def _validate_after_run(
        self, *, job_metadata: JobMetadata, working_memory: WorkingMemory, pipe_run_params: PipeRunParams, output_name: str | None = None
    ):
        pass

    async def _evaluate_expression(
        self,
        *,
        working_memory: WorkingMemory,
    ) -> str:
        """Evaluate the conditional expression and select the appropriate pipe.

        Args:
            working_memory: The working memory context for evaluation

        Returns:
            The evaluated expression
        """
        evaluated_expression = await render_template(
            template=self.expression,
            category=TemplateCategory.EXPRESSION,
            context=working_memory.generate_context(),
        )

        if self.add_alias_from_expression_to:
            working_memory.add_alias(
                alias=evaluated_expression,
                target=self.add_alias_from_expression_to,
            )

        return evaluated_expression

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
        evaluated_expression = await self._evaluate_expression(working_memory=working_memory)
        # Select the outcome based on the evaluated expression
        outcome = self.outcome_map.get(evaluated_expression, self.default_outcome)

        # Capture execution data for the graph tracer
        execution_data_dict: dict[str, Any] = {
            "evaluated_expression": evaluated_expression,
            "selected_outcome": str(outcome),
        }

        # Handle continue case (phase 1): `continue` resolves the declared output as
        # ABSENT — a declared-absent record with provenance, memory otherwise unchanged. A previous
        # main stuff stays under its own name (the migration idiom: consume it explicitly
        # downstream); it no longer passes through as this pipe's output.
        if SpecialOutcome.is_continue(outcome):
            self._register_execution_data(job_metadata=job_metadata, execution_data=execution_data_dict)
            # The reason names only the pipe and the outcome: a pipe that force-unwraps this output quotes it to the caller
            # under STRICT disclosure, and the value the expression rendered can be literal text of a condition a host
            # library declared. The execution data above keeps that value.
            self._record_declared_absent_output(
                working_memory=working_memory,
                output_name=output_name,
                reason=f"PipeCondition '{self.code}' resolved to its 'continue' outcome",
            )
            return PipeOutput(working_memory=working_memory, pipeline_run_id=job_metadata.run_metadata.pipeline_run_id)

        if SpecialOutcome.is_fail(outcome):
            self._register_execution_data(job_metadata=job_metadata, execution_data=execution_data_dict)
            # The caller's method maps this outcome to 'fail' on purpose, a refusal of the run it was given. The
            # message names only the pipe: the value the expression rendered can be literal text of the expression,
            # or an outcome key, of a condition a host library declared. The execution data above keeps that value.
            msg = f"PipeCondition '{self.code}' failed with outcome: {outcome}."
            raise PipeRunError(message=msg, run_mode=pipe_run_params.run_mode, pipe_code=self.code).as_caller_fault(
                user_action=UserAction(
                    kind=UserActionKind.CHANGE_INPUT,
                    detail=(
                        f"PipeCondition '{self.code}' refuses this run on purpose: change the inputs so that its expression "
                        "selects another outcome, or map that outcome to a pipe or to 'continue'."
                    ),
                )
            )

        chosen_pipe = get_required_pipe(pipe_code=outcome)

        # Get required variables and validate they exist in working memory
        # Extract root names from full paths for looking up stuffs in working memory
        required_variables = chosen_pipe.required_variables()
        # TODO: Merge `needed_inputs` and `required_variables` methods for cleaner code.
        required_stuff_names = {get_root_from_dotted_path(req_var) for req_var in required_variables if not req_var.startswith("_")}
        # A variable declared optional (`?`) on the chosen pipe is never presence-required (the
        # `@?` fix, D7): the pipe runs with the slot absent and its guarded templates handle it.
        required_stuff_names = {
            name
            for name in required_stuff_names
            if not ((declared_spec := chosen_pipe.inputs.root.get(name)) is not None and declared_spec.presence.is_optional)
        }
        # A recorded absence is not a miss: the chosen pipe's own gate applies the trichotomy
        # (skip / run / force). Only a name with neither a value nor a record is a hard miss.
        missing_names = working_memory.list_missing_names(names=required_stuff_names)
        if missing_names:
            # The caller's request or an earlier step of their method left out what the chosen pipe needs. The
            # message names only the pipes and the input names.
            missing_names_str = ", ".join(missing_names)
            msg = f"PipeCondition '{self.code}' chose pipe '{outcome}', whose required inputs are missing: {missing_names_str}."
            raise PipeRunError(message=msg, run_mode=pipe_run_params.run_mode, pipe_code=self.code).as_caller_fault(
                user_action=UserAction(
                    kind=UserActionKind.CHANGE_INPUT,
                    detail=f"Provide the missing required inputs of '{outcome}', which PipeCondition '{self.code}' chose: {missing_names_str}.",
                )
            )

        pipe_output = await get_pipe_router().run(
            pipe_job=PipeJobFactory.make_pipe_job(
                pipe=get_required_pipe(pipe_code=outcome),
                job_metadata=job_metadata,
                working_memory=working_memory,
                pipe_run_params=pipe_run_params,
                output_name=output_name,
                library_crate=library_crate,
            ),
        )
        self._register_execution_data(job_metadata=job_metadata, execution_data=execution_data_dict)
        return pipe_output

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
        # Validate that the expression template is valid
        try:
            detect_jinja2_required_variables(
                template_category=TemplateCategory.EXPRESSION,
                template_source=self.expression,
            )
        except Jinja2DetectVariablesError as exc:
            # Nothing is logged here: the refusal raised below is the failure, and whoever handles it reports it.
            # The expression is the caller's own method. The message quotes neither the expression nor the parser's
            # diagnosis, which names the token it stopped at: the condition may be a host library's, whose text
            # must not reach the caller. The line locates the fault. It is raised from the parser's own error,
            # past the `Jinja2DetectVariablesError` that quotes the expression: a run failure reports the innermost
            # Pipelex error on its chain (`find_root_fault`), which must be this refusal.
            msg = f"Dry run failed for pipe '{self.code}' (PipeCondition): its expression {describe_expression_parse_failure(error=exc)}."
            raise PipeRunError(message=msg, run_mode=pipe_run_params.run_mode, pipe_code=self.code).as_caller_fault(
                user_action=UserAction(
                    kind=UserActionKind.CHANGE_INPUT,
                    detail=f"Fix the expression of PipeCondition '{self.code}' so that it parses as a Jinja2 expression.",
                )
            ) from exc.__cause__

        # Validate that all values in the outcomes map (appart from special outcomes) do exist as pipe codes
        all_pipe_codes = set(self.outcome_map.values())
        if self.default_outcome:
            all_pipe_codes.add(self.default_outcome)
        all_pipe_codes -= set(SpecialOutcome.value_list())

        missing_pipes = sorted(pipe_code for pipe_code in all_pipe_codes if not get_optional_pipe(pipe_code=pipe_code))

        if missing_pipes:
            # The caller's method names these pipes in its outcomes. The message names only the pipe codes.
            missing_pipes_str = ", ".join(missing_pipes)
            msg = f"Dry run failed for PipeCondition '{self.code}': its outcomes name pipes that do not exist: {missing_pipes_str}."
            raise PipeRunError(message=msg, run_mode=pipe_run_params.run_mode, pipe_code=self.code).as_caller_fault(
                user_action=UserAction(
                    kind=UserActionKind.CHANGE_INPUT,
                    detail=f"Declare the pipes {missing_pipes_str}, or change the outcomes of PipeCondition '{self.code}' to name existing pipes.",
                )
            )

        # A dry run cannot know which outcome a live run takes, so every pipe outcome runs. Each
        # outcome but the last runs on a copy of the memory and run params this condition received,
        # as PipeParallel runs its branches: no outcome sees what a sibling wrote, and the memory
        # this condition leaves is the one a live run choosing the last outcome would leave. The
        # last outcome is the default outcome's pipe, so the steps after the condition read the
        # value a live run falls back to when nothing matches, and the order is a property of the
        # method rather than of set iteration order. The graph then shows the condition's result
        # as one stuff that every outcome produces, which the merge registered below records.
        received_stuff_codes = {stuff.stuff_code for stuff in working_memory.root.values()}
        outcome_slots: list[DryRunOutcomeSlot] = []
        outcome_pipe_codes = self._dry_run_outcome_order()
        for outcome_index, pipe_code in enumerate(outcome_pipe_codes):
            is_last_outcome = outcome_index == len(outcome_pipe_codes) - 1
            outcome_pipe = get_required_pipe(pipe_code=pipe_code)
            outcome_output = await outcome_pipe.run_pipe(
                job_metadata=job_metadata,
                working_memory=working_memory if is_last_outcome else working_memory.make_deep_copy(),
                pipe_run_params=pipe_run_params if is_last_outcome else pipe_run_params.make_deep_copy(),
                output_name=output_name,
                library_crate=library_crate,
            )
            outcome_slots.append(
                DryRunOutcomeSlot(
                    declared_concept=outcome_pipe.output.concept.code,
                    declared_list=bool(outcome_pipe.output.multiplicity),
                    stuff=outcome_output.working_memory.get_optional_main_stuff(),
                )
            )
        self._register_dry_run_output_merge(
            job_metadata=job_metadata,
            pipe_run_params=pipe_run_params,
            received_stuff_codes=received_stuff_codes,
            outcome_slots=outcome_slots,
        )
        execution_data_dict: dict[str, Any] = {
            "evaluated_expression": "dry_run",
            "selected_outcome": "all_outcomes",
        }
        self._register_execution_data(job_metadata=job_metadata, execution_data=execution_data_dict)
        # Dry-run parity with the live `continue` arm: with only special outcomes mapped, no pipe
        # dry-ran into this memory. When `continue` is reachable the declared output resolves
        # absent, memory otherwise unchanged (the static rule "continue-reachable ⇒ `?` output" is
        # Step D's OPTIONAL_OUTPUT_REQUIRED). A fail-only condition has no absent arm — every live
        # path raises — so fabricating an absence would let dry-run bless a method that can only
        # fail at runtime.
        if not self.pipe_dependencies():
            if not self._continue_reachable:
                # The caller's method maps every outcome to 'fail'. The message names only the pipe.
                msg = (
                    f"PipeCondition '{self.code}' maps every outcome (and the default) to 'fail': "
                    f"every live run of this pipe raises. Map at least one outcome to a pipe or to 'continue'."
                )
                raise PipeRunError(message=msg, run_mode=pipe_run_params.run_mode, pipe_code=self.code).as_caller_fault(
                    user_action=UserAction(
                        kind=UserActionKind.CHANGE_INPUT,
                        detail=f"Map at least one outcome of PipeCondition '{self.code}' to a pipe or to 'continue'.",
                    )
                )
            self._record_declared_absent_output(
                working_memory=working_memory,
                output_name=output_name,
                reason=f"dry run of PipeCondition '{self.code}': all outcomes are special, the declared output resolves absent",
            )
        return PipeOutput(working_memory=working_memory, pipeline_run_id=job_metadata.run_metadata.pipeline_run_id)

    def _dry_run_outcome_order(self) -> list[str]:
        """The pipe outcomes in the order a dry run runs them: sorted, with the default outcome's pipe last."""
        pipe_codes = sorted(self.pipe_dependencies())
        if self.default_outcome in pipe_codes:
            pipe_codes.remove(self.default_outcome)
            pipe_codes.append(self.default_outcome)
        return pipe_codes

    def _register_dry_run_output_merge(
        self,
        *,
        job_metadata: JobMetadata,
        pipe_run_params: PipeRunParams,
        received_stuff_codes: set[str],
        outcome_slots: list[DryRunOutcomeSlot],
    ) -> None:
        """Record that every outcome's output is this condition's one output stuff, for the graph.

        The shared stuff is the last outcome's, which the steps after the condition already read.
        Only a stuff minted inside the condition is merged: an outcome handing back a stuff it was
        given would otherwise drag that stuff's own producer into the condition's result. When the
        merged outcomes write or declare different concepts or multiplicities, the shared stuff is
        typed by this condition's declared output, the one typing that covers them all. The
        declarations count because an outcome's stuff can stand for several: a nested condition
        hands back only its last outcome's stuff, while its declaration covers all of them. A
        record carrying a typing and no merged digest is still left when the outcomes already
        share the stuff code, as under a batch that gives its branch its own stuff code.

        Args:
            job_metadata: The condition's job metadata, whose trace context names its graph node.
            pipe_run_params: The condition's run params, carrying the invocation's output multiplicity.
            received_stuff_codes: The stuff codes in the memory the condition received.
            outcome_slots: What each outcome left in the slot and what it declares, in run order.
        """
        trace_context = job_metadata.trace_context
        if trace_context is None or not trace_context.emit_graph_events or trace_context.parent_node_id is None:
            return
        tracer_manager = GraphTracerManager.get_instance()
        if tracer_manager is None or not outcome_slots:
            return
        shared_slot = outcome_slots[-1]
        shared_stuff = shared_slot.stuff
        if shared_stuff is None or shared_stuff.stuff_code in received_stuff_codes:
            return
        # The outcomes that wrote a stuff minted inside the condition. Their stuffs can already carry
        # the shared digest: a condition run as a batch's branch is given the branch's stuff code,
        # which every outcome mints under, so only the typing is left to record.
        merging_slots = [slot for slot in outcome_slots[:-1] if slot.stuff is not None and slot.stuff.stuff_code not in received_stuff_codes]
        if not merging_slots:
            return
        merging_slots.append(shared_slot)
        merged_digests = sorted(
            {slot.stuff.stuff_code for slot in merging_slots if slot.stuff is not None and slot.stuff.stuff_code != shared_stuff.stuff_code}
        )

        shared_typing: ConditionOutputTyping | None = None
        if len({slot.written_typing for slot in merging_slots}) > 1 or len({slot.declared_typing for slot in merging_slots}) > 1:
            multiplicity_resolution = output_multiplicity_to_apply(
                base_multiplicity=self.output.multiplicity,
                override_multiplicity=pipe_run_params.output_multiplicity,
            )
            shared_typing = ConditionOutputTyping(
                concept=self.output.concept.code,
                multiplicity=True if multiplicity_resolution.is_multiple_outputs_enabled else None,
            )

        if not merged_digests and shared_typing is None:
            return

        tracer_manager.register_condition_output_merge(
            lookup_key=trace_context.lookup_key,
            merge=ConditionOutputMerge(
                condition_node_id=trace_context.parent_node_id,
                shared_digest=shared_stuff.stuff_code,
                merged_digests=merged_digests,
                shared_typing=shared_typing,
            ),
        )

    def _record_declared_absent_output(self, *, working_memory: WorkingMemory, output_name: str | None, reason: str) -> None:
        """Resolve this pipe's declared output as a declared-absent record (the `continue` arm)."""
        record = AbsenceRecord(
            variable_name=output_name or MAIN_STUFF_NAME,
            kind=AbsenceKind.DECLARED_ABSENT,
            reason=reason,
            producing_pipe=self.code,
        )
        working_memory.record_new_main_absence(record)
