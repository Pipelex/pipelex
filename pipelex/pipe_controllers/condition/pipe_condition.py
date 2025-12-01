from typing import Literal

import shortuuid
from typing_extensions import override

from pipelex import log
from pipelex.cogt.templating.template_category import TemplateCategory
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.exceptions import WorkingMemoryStuffNotFoundError
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.pipes.exceptions import PipeValidationError, PipeValidationErrorType
from pipelex.core.pipes.inputs.input_requirements import InputRequirements
from pipelex.core.pipes.inputs.input_requirements_factory import InputRequirementsFactory
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.hub import get_content_generator, get_optional_pipe, get_pipe_router, get_pipeline_tracker, get_required_pipe
from pipelex.pipe_controllers.condition.pipe_condition_details import PipeConditionDetails
from pipelex.pipe_controllers.condition.special_outcome import SpecialOutcome
from pipelex.pipe_controllers.pipe_controller import PipeController
from pipelex.pipe_run.exceptions import PipeRunError
from pipelex.pipe_run.pipe_job_factory import PipeJobFactory
from pipelex.pipe_run.pipe_run_params import PipeRunParams
from pipelex.pipeline.job_metadata import JobMetadata
from pipelex.tools.jinja2.jinja2_errors import Jinja2DetectVariablesError
from pipelex.tools.jinja2.jinja2_required_variables import detect_jinja2_required_variables

ConditionOutcomeMap = dict[str, str | SpecialOutcome]


class PipeCondition(PipeController):
    type: Literal["PipeCondition"] = "PipeCondition"
    expression: str
    outcome_map: ConditionOutcomeMap
    default_outcome: str | SpecialOutcome
    add_alias_from_expression_to: str | None = None

    @property
    def mapped_pipe_codes(self) -> set[str]:
        codes = set(self.outcome_map.values())
        if self.default_outcome:
            codes.add(self.default_outcome)
        return codes - set(SpecialOutcome.value_list())

    def _make_pipe_condition_details(self, evaluated_expression: str, chosen_pipe_code: str) -> PipeConditionDetails:
        return PipeConditionDetails(
            code=shortuuid.uuid()[:5],
            test_expression=self.expression,
            outcomes=self.outcome_map,
            default_pipe_code=self.default_outcome,
            evaluated_expression=evaluated_expression,
            chosen_pipe_code=chosen_pipe_code,
        )

    @override
    def pipe_dependencies(self) -> set[str]:
        return self.mapped_pipe_codes

    @override
    def required_variables(self) -> set[str]:
        required_variables: set[str] = set()
        # Variables from the expression/expression_template
        expression_required_variables = detect_jinja2_required_variables(
            template_category=TemplateCategory.EXPRESSION,
            template_source=self.expression,
        )
        required_variables.update(expression_required_variables)

        # Variables from the outcomes map and default_outcome
        for pipe_code in self.pipe_dependencies():
            required_variables.update(get_required_pipe(pipe_code=pipe_code).required_variables())
        return required_variables

    @override
    def needed_inputs(self, visited_pipes: set[str] | None = None) -> InputRequirements:
        if visited_pipes is None:
            visited_pipes = set()

        # If we've already visited this pipe, stop recursion
        if self.code in visited_pipes:
            return InputRequirementsFactory.make_empty()

        # Add this pipe to visited set for recursive calls
        visited_pipes_with_current = visited_pipes | {self.code}

        needed_inputs = InputRequirementsFactory.make_empty()

        # 1. Add the variables from the expression/expression_template
        required_variables = detect_jinja2_required_variables(
            template_category=TemplateCategory.EXPRESSION,
            template_source=self.expression,
        )

        for var_name in required_variables:
            if not var_name.startswith("_"):  # exclude internal variables starting with `_`
                # We don't know the concept code from just the variable name,
                # so we'll use a generic placeholder that will be validated later
                needed_inputs.add_requirement(
                    variable_name=var_name,
                    concept=ConceptFactory.make_native_concept(
                        native_concept_code=NativeConceptCode.ANYTHING,
                    ),
                )

        # 2. Add the inputs needed by all possible target pipes
        for pipe_code in self.mapped_pipe_codes:
            pipe = get_required_pipe(pipe_code=pipe_code)
            # Use the centralized recursion detection
            pipe_needed_inputs = pipe.needed_inputs(visited_pipes_with_current)

            for input_name, requirement in pipe_needed_inputs.items:
                needed_inputs.add_requirement(variable_name=input_name, concept=requirement.concept)
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
        The output of the pipe condition should match the output of all the conditional pipes, and the default pipe.
        """
        for pipe_code in self.mapped_pipe_codes:
            pipe = get_required_pipe(pipe_code=pipe_code)
            if self.output.concept_string not in {
                pipe.output.concept_string,
                NativeConceptCode.DYNAMIC.concept_string,
                NativeConceptCode.ANYTHING.concept_string,
            }:
                msg = (
                    f"The output concept code '{self.output.concept_string}' of the pipe '{self.code}' is not "
                    f"matching the output concept code '{pipe.output.concept_string}' of the pipe '{pipe_code}'"
                )
                raise PipeValidationError(
                    message=msg,
                    error_type=PipeValidationErrorType.INADEQUATE_OUTPUT_CONCEPT,
                    domain=self.domain,
                    pipe_code=self.code,
                    provided_concept_code=pipe.output.concept_string,
                    required_concept_codes=[self.output.concept_string],
                )

    # TODO: Restore this validation. The problem lies with needed_inputs that construct Anything concepts.
    # @override
    # async def validate_before_run(
    #     self,
    #     job_metadata: JobMetadata,
    #     working_memory: WorkingMemory,
    #     pipe_run_params: PipeRunParams,
    #     output_name: str | None = None,
    # ):
    #     evaluated_expression = await get_content_generator().make_templated_text(
    #         context=working_memory.generate_context(),
    #         template=self.expression,
    #         template_category=TemplateCategory.EXPRESSION,
    #     )
    #     if not evaluated_expression or evaluated_expression == "None":
    #         error_msg = f"PipeCondition '{self.code}': Conditional expression returned no result"
    #         raise PipeRunError(
    #             message=error_msg,
    #             run_mode=pipe_run_params.run_mode,
    #         )

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
        evaluated_expression = await get_content_generator().make_templated_text(
            context=working_memory.generate_context(),
            template=self.expression,
            template_category=TemplateCategory.EXPRESSION,
        )

        log.verbose(f"add_alias: {evaluated_expression} -> {self.add_alias_from_expression_to}")
        if self.add_alias_from_expression_to:
            working_memory.add_alias(
                alias=evaluated_expression,
                target=self.add_alias_from_expression_to,
            )

        return evaluated_expression

    @override
    async def _run_controller_pipe(
        self,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: str | None = None,
    ) -> PipeOutput:
        log.verbose(f"{self.class_name} generating a '{self.output.code}'")

        # TODO: restore pipe_layer feature
        # pipe_run_params.push_pipe_code(pipe_code=pipe_code)

        evaluated_expression = await self._evaluate_expression(working_memory=working_memory)

        # Select the outcome based on the evaluated expression
        outcome = self.outcome_map.get(evaluated_expression, self.default_outcome)

        # Handle continue case
        if SpecialOutcome.is_continue(outcome):
            log.dev(f"PipeCondition '{self.code}' continued with outcome: {outcome}. Evaluated expression: {evaluated_expression}")
            return PipeOutput(working_memory=working_memory)

        if SpecialOutcome.is_fail(outcome):
            msg = f"PipeCondition '{self.code}' failed with outcome: {outcome}. Evaluated expression: {evaluated_expression}"
            raise PipeRunError(message=msg, run_mode=pipe_run_params.run_mode)

        chosen_pipe = get_required_pipe(pipe_code=outcome)

        # Create condition details for tracking
        condition_details = self._make_pipe_condition_details(
            evaluated_expression=self.expression,
            chosen_pipe_code=chosen_pipe.code,
        )

        # Get required variables and validate they exist in working memory
        required_variables = chosen_pipe.required_variables()
        required_stuff_names = {required_variable for required_variable in required_variables if not required_variable.startswith("_")}
        try:
            required_stuffs = working_memory.get_stuffs(names=required_stuff_names)
        except WorkingMemoryStuffNotFoundError as exc:
            pipe_condition_path = [*pipe_run_params.pipe_layers, self.code]
            pipe_condition_path_str = ".".join(pipe_condition_path)
            error_details = f"PipeCondition '{pipe_condition_path_str}', required_variables: {required_variables}, missing: '{exc.variable_name}'"
            msg = f"Some required stuff(s) not found: {error_details}"
            raise PipeRunError(message=msg, run_mode=pipe_run_params.run_mode) from exc

        # Track condition steps
        for required_stuff in required_stuffs:
            get_pipeline_tracker().add_condition_step(
                from_stuff=required_stuff,
                to_condition=condition_details,
                condition_expression=self.expression,
                pipe_layer=pipe_run_params.pipe_layers,
                comment="PipeCondition required for condition",
            )

        # Execute the chosen pipe
        log.verbose(f"Chosen pipe: {chosen_pipe.code}")
        pipe_output = await get_pipe_router().run(
            pipe_job=PipeJobFactory.make_pipe_job(
                pipe=chosen_pipe,
                job_metadata=job_metadata,
                working_memory=working_memory,
                pipe_run_params=pipe_run_params,
                output_name=output_name,
            ),
        )

        # Track choice step
        get_pipeline_tracker().add_choice_step(
            from_condition=condition_details,
            to_stuff=pipe_output.main_stuff,
            pipe_layer=pipe_run_params.pipe_layers,
            comment="PipeCondition chosen pipe",
        )
        return pipe_output

    @override
    async def _dry_run_controller_pipe(
        self,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: str | None = None,
    ) -> PipeOutput:
        """Dry run implementation for PipeCondition.
        Validates that all required inputs are present, expression is valid, and target pipes exist.
        """
        log.verbose(f"PipeCondition: dry run controller pipe: {self.code}")
        # 1. Validate that all required inputs are present in the working memory
        needed_inputs = self.needed_inputs()
        missing_input_names: list[str] = []

        for named_input_requirement in needed_inputs.named_input_requirements:
            if not working_memory.get_optional_stuff(named_input_requirement.variable_name):
                missing_input_names.append(named_input_requirement.variable_name)

        if missing_input_names:
            log.error(f"Dry run failed: missing required inputs: {missing_input_names}")
            raise PipeRunError(
                message=f"Dry run failed for pipe '{self.code}' (PipeCondition): missing required inputs: {', '.join(missing_input_names)}",
                run_mode=pipe_run_params.run_mode,
            )

        # 2. Validate that the expression template is valid
        try:
            required_variables = detect_jinja2_required_variables(
                template_category=TemplateCategory.EXPRESSION,
                template_source=self.expression,
            )
            log.verbose(f"Expression template is valid, requires variables: {required_variables}")
        except Jinja2DetectVariablesError as exc:
            log.error(f"Dry run failed: could not detect required variables from expression template: {exc}")
            msg = (
                f"Dry run failed for pipe '{self.code}' (PipeCondition): could not detect required variables "
                f"from expression template: {exc}\nTemplate:\n'{self.expression}'"
            )
            raise PipeRunError(message=msg, run_mode=pipe_run_params.run_mode) from exc

        # 3. Validate that all values in the outcomes map (appart from special outcomes) do exist as pipe codes
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
            raise PipeRunError(message=msg, run_mode=pipe_run_params.run_mode)

        # Here, it should launch the dry run of all the pipes in the outcomes map
        for pipe_code in self.mapped_pipe_codes:
            pipe = get_required_pipe(pipe_code=pipe_code)
            await pipe.run_pipe(
                job_metadata=job_metadata,
                working_memory=working_memory,
                pipe_run_params=pipe_run_params,
            )
        return PipeOutput(working_memory=working_memory)
