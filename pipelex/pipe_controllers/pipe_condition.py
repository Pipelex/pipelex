from typing import Dict, List, Optional, Set, cast

import shortuuid
from pydantic import model_validator
from typing_extensions import Self, override

from pipelex import log
from pipelex.config import StaticValidationReaction, get_config
from pipelex.core.pipe_input_spec import PipeInputSpec
from pipelex.core.pipe_output import PipeOutput
from pipelex.core.pipe_run_params import PipeRunParams
from pipelex.core.working_memory import WorkingMemory
from pipelex.exceptions import (
    DryRunError,
    PipeConditionError,
    PipeDefinitionError,
    PipeExecutionError,
    PipeInputError,
    StaticValidationError,
    StaticValidationErrorType,
    WorkingMemoryStuffNotFoundError,
)
from pipelex.hub import get_pipe_router, get_pipeline_tracker, get_required_pipe
from pipelex.pipe_controllers.pipe_condition_details import PipeConditionDetails
from pipelex.pipe_controllers.pipe_controller import PipeController
from pipelex.pipe_operators.pipe_jinja2 import PipeJinja2, PipeJinja2Output
from pipelex.pipeline.job_metadata import JobCategory, JobMetadata
from pipelex.tools.typing.validation_utils import has_exactly_one_among_attributes_from_list


class PipeCondition(PipeController):
    expression_template: Optional[str] = None
    expression: Optional[str] = None
    pipe_map: Dict[str, str]
    default_pipe_code: Optional[str] = None
    add_alias_from_expression_to: Optional[str] = None

    @model_validator(mode="after")
    def validate_expression(self) -> Self:
        if not has_exactly_one_among_attributes_from_list(self, attributes_list=["expression_template", "expression"]):
            raise PipeDefinitionError("PipeCondition should have exactly one of expression_template or expression")
        return self

    @property
    def applied_expression_template(self) -> str:
        if self.expression_template:
            return self.expression_template
        elif self.expression:
            return "{{ " + self.expression + " }}"
        else:
            raise PipeExecutionError("No expression or expression_template provided")

    def _make_pipe_condition_details(self, evaluated_expression: str, chosen_pipe_code: str) -> PipeConditionDetails:
        return PipeConditionDetails(
            code=shortuuid.uuid()[:5],
            test_expression=self.expression or self.applied_expression_template,
            pipe_map=self.pipe_map,
            default_pipe_code=self.default_pipe_code,
            evaluated_expression=evaluated_expression,
            chosen_pipe_code=chosen_pipe_code,
        )

    def needed_inputs(self) -> PipeInputSpec:
        """
        Calculate the inputs needed by this PipeCondition.

        The inputs are:
        1. Inputs needed by the condition expression/expression_template
        2. Inputs needed by ALL possible target pipes (since we don't know which will be chosen)
        """
        needed_inputs = PipeInputSpec()

        # Get inputs needed by the condition expression
        pipe_jinja2 = PipeJinja2(
            code="adhoc_for_needed_inputs",
            domain=self.domain,
            jinja2=self.applied_expression_template,
        )
        expression_required_vars = pipe_jinja2.required_variables()

        # Add expression variables as needed inputs (excluding internal variables starting with _)
        for var_name in expression_required_vars:
            if not var_name.startswith("_"):
                # We don't know the concept code from just the variable name,
                # so we'll use a generic placeholder that will be validated later
                needed_inputs.add_requirement(variable_name=var_name, concept_code=f"{self.domain}.Unknown")

        # Get inputs needed by all possible target pipes
        target_pipe_codes = list(self.pipe_map.values())
        if self.default_pipe_code:
            target_pipe_codes.append(self.default_pipe_code)

        for pipe_code in target_pipe_codes:
            pipe = get_required_pipe(pipe_code=pipe_code)

            # Get the inputs needed by this target pipe
            target_pipe_needed_inputs: PipeInputSpec
            if hasattr(pipe, "needed_inputs") and callable(getattr(pipe, "needed_inputs", None)):
                # If the pipe has a needed_inputs method, use it
                needed_inputs_method = getattr(pipe, "needed_inputs")
                target_pipe_needed_inputs = needed_inputs_method()
            else:
                # Otherwise, use the pipe's declared inputs
                target_pipe_needed_inputs = pipe.inputs

            # Add all inputs from this target pipe
            for input_name, concept_code in target_pipe_needed_inputs.root.items():
                needed_inputs.add_requirement(variable_name=input_name, concept_code=concept_code)

        return needed_inputs

    @model_validator(mode="after")
    def validate_inputs(self) -> Self:
        if not self.pipe_map:
            raise ValueError(f"Pipe {self.code} (PipeCondition) must have at least one mapping in pipe_map")

        # Skip validation during model creation - it will be done in validate_with_libraries()
        return self

    def _validate_inputs(self):
        """
        Validate that the inputs declared for this PipeCondition match what is actually needed.
        """
        static_validation_config = get_config().pipelex.static_validation_config
        default_reaction = static_validation_config.default_reaction
        reactions = static_validation_config.reactions

        the_needed_inputs = self.needed_inputs()

        # Check all required variables are in the inputs
        for required_variable_name, _, _ in the_needed_inputs.detailed_requirements:
            if required_variable_name not in self.inputs.variables:
                missing_input_var_error = StaticValidationError(
                    error_type=StaticValidationErrorType.MISSING_INPUT_VARIABLE,
                    domain_code=self.domain,
                    pipe_code=self.code,
                    variable_names=[required_variable_name],
                )
                match reactions.get(StaticValidationErrorType.MISSING_INPUT_VARIABLE, default_reaction):
                    case StaticValidationReaction.IGNORE:
                        pass
                    case StaticValidationReaction.LOG:
                        log.error(missing_input_var_error.desc())
                    case StaticValidationReaction.RAISE:
                        raise missing_input_var_error

        # Check that all declared inputs are actually needed
        for input_name in self.inputs.variables:
            if input_name not in the_needed_inputs.required_names:
                extraneous_input_var_error = StaticValidationError(
                    error_type=StaticValidationErrorType.EXTRANEOUS_INPUT_VARIABLE,
                    domain_code=self.domain,
                    pipe_code=self.code,
                    variable_names=[input_name],
                )
                match reactions.get(StaticValidationErrorType.EXTRANEOUS_INPUT_VARIABLE, default_reaction):
                    case StaticValidationReaction.IGNORE:
                        pass
                    case StaticValidationReaction.LOG:
                        log.error(extraneous_input_var_error.desc())
                    case StaticValidationReaction.RAISE:
                        raise extraneous_input_var_error

    @override
    def validate_with_libraries(self):
        """
        Perform full validation after all libraries are loaded.
        This is called after all pipes and concepts are available.
        """
        self._validate_inputs()

    @override
    def pipe_dependencies(self) -> Set[str]:
        pipe_codes = list(self.pipe_map.values())
        if self.default_pipe_code:
            pipe_codes.append(self.default_pipe_code)
        return set(pipe_codes)

    @override
    async def _run_controller_pipe(
        self,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: Optional[str] = None,
    ) -> PipeOutput:
        log.dev(f"{self.class_name} generating a '{self.output_concept_code}'")

        # TODO: restore pipe_layer feature
        # pipe_run_params.push_pipe_code(pipe_code=pipe_code)

        pipe_jinja2 = PipeJinja2(
            code="adhoc_for_pipe_condition",
            domain=self.domain,
            jinja2=self.applied_expression_template,
        )
        jinja2_job_metadata = job_metadata.copy_with_update(
            updated_metadata=JobMetadata(
                job_category=JobCategory.JINJA2_JOB,
            )
        )
        log.debug(f"Jinja2 expression: {self.applied_expression_template}")
        # evaluated_expression = (
        #     await pipe_jinja2.run_pipe(
        #         job_metadata=jinja2_job_metadata,
        #         working_memory=working_memory,
        #         pipe_run_params=pipe_run_params,
        #     )
        # ).rendered_text.strip()
        # TODO: restore the possibility above, without need to explicitly cast the output
        pipe_output_1: PipeOutput = await pipe_jinja2.run_pipe(
            job_metadata=jinja2_job_metadata,
            working_memory=working_memory,
            pipe_run_params=pipe_run_params,
        )
        pipe_jinja2_output = cast(PipeJinja2Output, pipe_output_1)
        evaluated_expression = pipe_jinja2_output.rendered_text.strip()

        if not evaluated_expression or evaluated_expression == "None":
            error_msg = f"Conditional expression returned an empty string in pipe {self.code}:"
            error_msg += f"\n\nExpression: {self.applied_expression_template}"
            raise PipeConditionError(error_msg)
        log.debug(f"evaluated_expression: '{evaluated_expression}'")

        log.debug(f"add_alias: {evaluated_expression} -> {self.add_alias_from_expression_to}")
        if self.add_alias_from_expression_to:
            working_memory.add_alias(
                alias=evaluated_expression,
                target=self.add_alias_from_expression_to,
            )

        chosen_pipe_code = self.pipe_map.get(evaluated_expression, self.default_pipe_code)
        if not chosen_pipe_code:
            error_msg = f"No pipe code found for evaluated expression '{evaluated_expression}' in pipe {self.code}:"
            error_msg += f"\n\nExpression: {self.applied_expression_template}"
            error_msg += f"\n\nPipe map: {self.pipe_map}"
            raise PipeConditionError(error_msg)

        condition_details = self._make_pipe_condition_details(
            evaluated_expression=evaluated_expression,
            chosen_pipe_code=chosen_pipe_code,
        )
        required_variables = pipe_jinja2.required_variables()
        log.debug(required_variables, title=f"Required variables for PipeCondition '{self.code}'")
        required_stuff_names = set([required_variable for required_variable in required_variables if not required_variable.startswith("_")])
        try:
            required_stuffs = working_memory.get_stuffs(names=required_stuff_names)
        except WorkingMemoryStuffNotFoundError as exc:
            pipe_condition_path = pipe_run_params.pipe_layers + [self.code]
            pipe_condition_path_str = ".".join(pipe_condition_path)
            error_details = f"PipeCondition '{pipe_condition_path_str}', required_variables: {required_variables}, missing: '{exc.variable_name}'"
            raise PipeInputError(f"Some required stuff(s) not found: {error_details}") from exc

        for required_stuff in required_stuffs:
            get_pipeline_tracker().add_condition_step(
                from_stuff=required_stuff,
                to_condition=condition_details,
                condition_expression=self.expression or self.applied_expression_template,
                pipe_layer=pipe_run_params.pipe_layers,
                comment="PipeCondition required for condition",
            )

        log.debug(f"Chosen pipe: {chosen_pipe_code}")
        pipe_output: PipeOutput = await get_pipe_router().run_pipe_code(
            pipe_code=chosen_pipe_code,
            job_metadata=job_metadata,
            working_memory=working_memory,
            pipe_run_params=pipe_run_params,
            output_name=output_name,
        )
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
        output_name: Optional[str] = None,
    ) -> PipeOutput:
        """
        Dry run implementation for PipeCondition.
        Validates that all required inputs are present, expression is valid, and target pipes exist.
        """
        log.info(f"PipeCondition: dry run controller pipe: {self.code}")

        # 1. Validate that all required inputs are present
        needed_inputs = self.needed_inputs()
        missing_input_names: List[str] = []

        for required_variable_name, _, _ in needed_inputs.detailed_requirements:
            if not working_memory.get_optional_stuff(required_variable_name):
                missing_input_names.append(required_variable_name)

        if missing_input_names:
            log.error(f"Dry run failed: missing required inputs: {missing_input_names}")
            raise DryRunError(
                message=f"Dry run failed for pipe '{self.code}' (PipeCondition): missing required inputs: {', '.join(missing_input_names)}",
                missing_inputs=missing_input_names,
                pipe_code=self.code,
            )

        # 2. Validate that the expression template is valid
        try:
            pipe_jinja2 = PipeJinja2(
                code="adhoc_for_pipe_condition_dry_run",
                domain=self.domain,
                jinja2=self.applied_expression_template,
            )
            # Get required variables to validate the template syntax
            required_variables = pipe_jinja2.required_variables()
            log.debug(f"Expression template is valid, requires variables: {required_variables}")
        except Exception as e:
            log.error(f"Dry run failed: invalid expression template: {e}")
            error_msg = (
                f"Dry run failed for pipe '{self.code}' (PipeCondition): invalid expression template '{self.applied_expression_template}': {e}"
            )
            raise DryRunError(
                message=error_msg,
                missing_inputs=[],
                pipe_code=self.code,
            )

        # 3. Validate that the expression can be evaluated (using dry run mode)
        try:
            jinja2_job_metadata = job_metadata.copy_with_update(
                updated_metadata=JobMetadata(
                    job_category=JobCategory.JINJA2_JOB,
                )
            )

            pipe_output_jinja2: PipeOutput = await pipe_jinja2.run_pipe(
                job_metadata=jinja2_job_metadata,
                working_memory=working_memory,
                pipe_run_params=pipe_run_params,
            )
            pipe_jinja2_output = cast(PipeJinja2Output, pipe_output_jinja2)
            evaluated_expression = pipe_jinja2_output.rendered_text.strip()

            if not evaluated_expression or evaluated_expression == "None":
                log.error("Dry run failed: expression evaluated to empty result")
                error_msg = (
                    f"Dry run failed for pipe '{self.code}' (PipeCondition): "
                    f"expression '{self.applied_expression_template}' evaluated to empty result"
                )
                raise DryRunError(
                    message=error_msg,
                    missing_inputs=[],
                    pipe_code=self.code,
                )

            log.debug(f"Expression successfully evaluated to: '{evaluated_expression}'")

        except DryRunError:
            # Re-raise DryRunError as is
            raise
        except Exception as e:
            log.error(f"Dry run failed: expression evaluation error: {e}")
            raise DryRunError(
                message=f"Dry run failed for pipe '{self.code}' (PipeCondition): expression evaluation failed: {e}",
                missing_inputs=[],
                pipe_code=self.code,
            )

        # 4. Validate that the evaluated expression maps to a valid pipe
        chosen_pipe_code = self.pipe_map.get(evaluated_expression, self.default_pipe_code)
        if not chosen_pipe_code:
            log.error(f"Dry run failed: no pipe found for expression result '{evaluated_expression}'")
            error_msg = (
                f"Dry run failed for pipe '{self.code}' (PipeCondition): no pipe code found for evaluated expression '{evaluated_expression}'. "
                f"Available mappings: {self.pipe_map}, default: {self.default_pipe_code}"
            )
            raise DryRunError(
                message=error_msg,
                missing_inputs=[],
                pipe_code=self.code,
            )

        # 5. Validate that the chosen pipe exists and can be dry run
        try:
            chosen_pipe = get_required_pipe(pipe_code=chosen_pipe_code)
            log.debug(f"Chosen pipe '{chosen_pipe_code}' exists and is accessible")

            # Run the chosen pipe in dry mode to validate it can execute
            pipe_output = await chosen_pipe.run_pipe(
                job_metadata=job_metadata,
                working_memory=working_memory,
                pipe_run_params=pipe_run_params,
                output_name=output_name,
            )

            log.info(f"PipeCondition dry run successful: expression '{evaluated_expression}' -> pipe '{chosen_pipe_code}'")
            return pipe_output

        except Exception as e:
            log.error(f"Dry run failed: chosen pipe '{chosen_pipe_code}' validation failed: {e}")
            raise DryRunError(
                message=f"Dry run failed for pipe '{self.code}' (PipeCondition): chosen pipe '{chosen_pipe_code}' failed validation: {e}",
                missing_inputs=[],
                pipe_code=self.code,
            )
