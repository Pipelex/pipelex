from typing import TYPE_CHECKING, Any, Literal

from typing_extensions import override

from pipelex import log
from pipelex.cogt.templating.template_category import TemplateCategory
from pipelex.cogt.templating.template_rendering import render_template
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory import WorkingMemory, WorkingMemoryStuffNotFoundError
from pipelex.core.pipes.exceptions import PipeValidationError, PipeValidationErrorType
from pipelex.core.pipes.inputs.input_stuff_specs import InputStuffSpecs
from pipelex.core.pipes.inputs.input_stuff_specs_factory import InputStuffSpecsFactory
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.hub import get_optional_pipe, get_pipe_router, get_required_pipe
from pipelex.pipe_controllers.condition.special_outcome import SpecialOutcome
from pipelex.pipe_controllers.pipe_controller import PipeController
from pipelex.pipe_run.exceptions import PipeRunError
from pipelex.pipe_run.pipe_job_factory import PipeJobFactory
from pipelex.pipe_run.pipe_run_params import PipeRunParams
from pipelex.pipeline.job_metadata import JobMetadata
from pipelex.tools.jinja2.exceptions import Jinja2DetectVariablesError
from pipelex.tools.jinja2.jinja2_required_variables import detect_jinja2_required_variables
from pipelex.tools.misc.string_utils import get_root_from_dotted_path

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
    def needed_inputs(self, visited_pipes: set[str] | None = None) -> InputStuffSpecs:
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
                )

        # Add the inputs needed by all possible target pipes
        for pipe_code in self.pipe_dependencies():
            pipe = get_required_pipe(pipe_code=pipe_code)
            # Use the centralized recursion detection
            pipe_needed_inputs = pipe.needed_inputs(visited_pipes_with_current)

            for input_name, stuff_spec in pipe_needed_inputs.items:
                needed_inputs.add_stuff_spec(variable_name=input_name, concept=stuff_spec.concept, multiplicity=stuff_spec.multiplicity)

        return needed_inputs

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
        self, job_metadata: JobMetadata, *, working_memory: WorkingMemory, pipe_run_params: PipeRunParams, output_name: str | None = None
    ):
        evaluated_expression = await render_template(
            template=self.expression,
            category=TemplateCategory.EXPRESSION,
            context=working_memory.generate_context(),
        )
        if not evaluated_expression or evaluated_expression == "None":
            error_msg = f"PipeCondition '{self.code}': Conditional expression returned no result"
            raise PipeRunError(
                pipe_code=self.code,
                message=error_msg,
                run_mode=pipe_run_params.run_mode,
            )

    @override
    async def _validate_after_run(
        self, job_metadata: JobMetadata, *, working_memory: WorkingMemory, pipe_run_params: PipeRunParams, output_name: str | None = None
    ):
        pass

    async def _evaluate_expression(
        self,
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

        # Handle continue case
        if SpecialOutcome.is_continue(outcome):
            log.dev(f"PipeCondition '{self.code}' continued with outcome: {outcome}. Evaluated expression: {evaluated_expression}")
            self._register_execution_data(job_metadata, execution_data=execution_data_dict)
            return PipeOutput(working_memory=working_memory)

        if SpecialOutcome.is_fail(outcome):
            self._register_execution_data(job_metadata, execution_data=execution_data_dict)
            msg = f"PipeCondition '{self.code}' failed with outcome: {outcome}. Evaluated expression: {evaluated_expression}"
            raise PipeRunError(message=msg, run_mode=pipe_run_params.run_mode, pipe_code=self.code)

        chosen_pipe = get_required_pipe(pipe_code=outcome)

        # Get required variables and validate they exist in working memory
        # Extract root names from full paths for looking up stuffs in working memory
        required_variables = chosen_pipe.required_variables()
        # TODO: Merge `needed_inputs` and `required_variables` methods for cleaner code.
        required_stuff_names = {get_root_from_dotted_path(req_var) for req_var in required_variables if not req_var.startswith("_")}
        try:
            working_memory.get_stuffs(names=required_stuff_names)
        except WorkingMemoryStuffNotFoundError as exc:
            pipe_condition_path = [*pipe_run_params.pipe_layers, self.code]
            pipe_condition_path_str = ".".join(pipe_condition_path)
            error_details = f"PipeCondition '{pipe_condition_path_str}', required_variables: {required_variables}, missing: '{exc.variable_name}'"
            msg = f"Some required stuff(s) not found: {error_details}"
            raise PipeRunError(message=msg, run_mode=pipe_run_params.run_mode, pipe_code=self.code) from exc

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
        self._register_execution_data(job_metadata, execution_data=execution_data_dict)
        return pipe_output

    @override
    async def _dry_run_controller_pipe(
        self,
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
            msg = (
                f"Dry run failed for pipe '{self.code}' (PipeCondition): could not detect required variables "
                f"from expression template: {exc}\nTemplate:\n'{self.expression}'"
            )
            raise PipeRunError(message=msg, run_mode=pipe_run_params.run_mode, pipe_code=self.code) from exc

        # Validate that all values in the outcomes map (appart from special outcomes) do exist as pipe codes
        all_pipe_codes = set(self.outcome_map.values())
        if self.default_outcome:
            all_pipe_codes.add(self.default_outcome)
        all_pipe_codes -= set(SpecialOutcome.value_list())

        missing_pipes = [pipe_code for pipe_code in all_pipe_codes if not get_optional_pipe(pipe_code=pipe_code)]

        if missing_pipes:
            msg = (
                f"Dry run failed for PipeCondition '{self.code}': missing pipes: {', '.join(missing_pipes)}. "
                f"Pipe map: {self.outcome_map}, default: {self.default_outcome}"
            )
            raise PipeRunError(message=msg, run_mode=pipe_run_params.run_mode, pipe_code=self.code)

        # Here, it should launch the dry run of all the pipes in the outcomes map
        for pipe_code in self.pipe_dependencies():
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
        self._register_execution_data(job_metadata, execution_data=execution_data_dict)
        return PipeOutput(working_memory=working_memory)
