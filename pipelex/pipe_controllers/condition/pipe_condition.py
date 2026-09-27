from typing import TYPE_CHECKING, Any, Literal

from jinja2 import TemplateSyntaxError
from typing_extensions import override

from pipelex import log
from pipelex.cogt.inference.error_classification import UserAction, UserActionKind
from pipelex.cogt.templating.template_rendering import render_template
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.absence import AbsenceKind, AbsenceRecord
from pipelex.core.memory.working_memory import MAIN_STUFF_NAME, WorkingMemory
from pipelex.core.pipes.exceptions import PipeRunError, PipeValidationError
from pipelex.core.pipes.inputs.input_stuff_specs import InputStuffSpecs
from pipelex.core.pipes.inputs.input_stuff_specs_factory import InputStuffSpecsFactory
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.interpreter_hub import get_optional_pipe, get_pipe_router, get_required_pipe
from pipelex.pipe_controllers.condition.special_outcome import SpecialOutcome
from pipelex.pipe_controllers.pipe_controller import PipeController
from pipelex.pipe_machinery.template_guard_lint import lint_optional_input_guards
from pipelex.pipe_run.pipe_job_factory import PipeJobFactory
from pipelex.pipe_run.pipe_run_params import PipeRunParams
from pipelex.system.job_metadata import JobMetadata
from pipelex.tools.jinja2.exceptions import Jinja2DetectVariablesError
from pipelex.tools.jinja2.jinja2_required_variables import detect_jinja2_required_variables
from pipelex.tools.jinja2.template_category import TemplateCategory
from pipelex.tools.misc.string_utils import get_root_from_dotted_path
from pipelex.validation_error_types import PipeValidationErrorType

if TYPE_CHECKING:
    from pipelex.libraries.library_crate import LibraryCrate

ConditionOutcomeMap = dict[str, str | SpecialOutcome]


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
    def needed_inputs(self, *, visited_pipes: set[str] | None = None) -> InputStuffSpecs:
        if visited_pipes is None:
            visited_pipes = set()

        # If we've already visited this pipe, stop recursion
        if self.pipe_ref in visited_pipes:
            return InputStuffSpecsFactory.make_empty()

        # Add this pipe to visited set for recursive calls
        visited_pipes_with_current = visited_pipes | {self.pipe_ref}

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
        # Guard-lint (D7): a declared-optional input referenced unguarded in the expression
        # would evaluate over an undefined variable when the value is absent.
        lint_optional_input_guards(
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
        # OPTIONAL_OUTPUT_REQUIRED (D5/D6): `continue` resolves the declared output as ABSENT
        # (design §14), so a `continue`-reachable condition must declare its output optional —
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

        log.verbose(f"add_alias: {evaluated_expression} -> {self.add_alias_from_expression_to}")
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

        # Handle continue case (design §14, phase 1): `continue` resolves the declared output as
        # ABSENT — a declared-absent record with provenance, memory otherwise unchanged. A previous
        # main stuff stays under its own name (the migration idiom: consume it explicitly
        # downstream); it no longer passes through as this pipe's output.
        if SpecialOutcome.is_continue(outcome):
            log.dev(f"PipeCondition '{self.code}' continued with outcome: {outcome}. Evaluated expression: {evaluated_expression}")
            self._register_execution_data(job_metadata=job_metadata, execution_data=execution_data_dict)
            self._record_declared_absent_output(
                working_memory=working_memory,
                output_name=output_name,
                reason=f"PipeCondition '{self.code}' resolved to 'continue' for evaluated expression '{evaluated_expression}'",
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
            full_paths = detect_jinja2_required_variables(
                template_category=TemplateCategory.EXPRESSION,
                template_source=self.expression,
            )
            required_variables = {get_root_from_dotted_path(path) for path in full_paths}
            log.verbose(f"Expression template is valid, requires variables: {required_variables}")
        except Jinja2DetectVariablesError as exc:
            log.error(f"Dry run failed: could not detect required variables from expression template: {exc}")
            # The expression is the caller's own method. The message quotes neither the expression nor the parser's
            # diagnosis, which names the token it stopped at: the condition may be a host library's, whose text
            # must not reach the caller. The line locates the fault. It is raised from the parser's own error,
            # past the `Jinja2DetectVariablesError` that quotes the expression: a run failure reports the innermost
            # Pipelex error on its chain (`find_root_fault`), which must be this refusal.
            msg = f"Dry run failed for pipe '{self.code}' (PipeCondition): its expression {_describe_expression_parse_failure(error=exc)}."
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

        # Here, it should launch the dry run of all the pipes in the outcomes map.
        # pipe_dependencies() is a set, and every branch dry-runs into the SAME
        # working memory under the SAME output_name — so the branch iterated last
        # is the one whose stuff the caller sees as this condition's output. Left
        # unsorted, that is string-hash order, which varies per process: the same
        # bundle dry-run twice yields two different graphs. Sort so the last writer
        # is a property of the method, not of PYTHONHASHSEED.
        for pipe_code in sorted(self.pipe_dependencies()):
            pipe = get_required_pipe(pipe_code=pipe_code)
            await pipe.run_pipe(
                job_metadata=job_metadata,
                working_memory=working_memory,
                pipe_run_params=pipe_run_params,
                output_name=output_name,
                library_crate=library_crate,
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

    def _record_declared_absent_output(self, *, working_memory: WorkingMemory, output_name: str | None, reason: str) -> None:
        """Resolve this pipe's declared output as a declared-absent record (the `continue` arm)."""
        record = AbsenceRecord(
            variable_name=output_name or MAIN_STUFF_NAME,
            kind=AbsenceKind.DECLARED_ABSENT,
            reason=reason,
            producing_pipe=self.code,
        )
        working_memory.record_new_main_absence(record)


def _describe_expression_parse_failure(*, error: Jinja2DetectVariablesError) -> str:
    """Say where a condition's expression fails to parse, in words that owe nothing to the expression.

    Every layer between Jinja2 and the condition puts the expression in its message, and Jinja2's own
    diagnosis quotes the token it stopped at, so no text of the error can be passed on. The parser's line,
    counted within the expression, is what locates the fault.
    """
    cause: BaseException | None = error.__cause__
    while cause is not None:
        if isinstance(cause, TemplateSyntaxError):
            return f"does not parse at line {cause.lineno} of that expression"
        cause = cause.__cause__
    return "does not parse"
