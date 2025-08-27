from typing import Dict, List, Optional, Set, Union, cast

import shortuuid
from pydantic import field_validator, model_validator
from typing_extensions import Self, override

from pipelex import log
from pipelex.config import StaticValidationReaction, get_config
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.concept_native import NATIVE_CONCEPTS_DATA, NativeConceptEnum
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.pipes.pipe_input_spec import PipeInputSpec
from pipelex.core.pipes.pipe_input_spec_blueprint import InputRequirementBlueprint
from pipelex.core.pipes.pipe_input_spec_factory import PipeInputSpecFactory
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.core.pipes.pipe_run_params import PipeRunParams
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
from pipelex.pipe_controllers.condition.pipe_condition_details import PipeConditionDetails, PipeConditionPipeMap
from pipelex.pipe_controllers.pipe_controller import PipeController
from pipelex.pipe_operators.jinja2.pipe_jinja2 import PipeJinja2Output
from pipelex.pipe_operators.jinja2.pipe_jinja2_blueprint import PipeJinja2Blueprint
from pipelex.pipe_operators.jinja2.pipe_jinja2_factory import PipeJinja2Factory
from pipelex.pipeline.job_metadata import JobCategory, JobMetadata
from pipelex.tools.typing.validation_utils import has_exactly_one_among_attributes_from_list


class PipeCondition(PipeController):
    expression_template: Optional[str] = None
    expression: Optional[str] = None
    # TODO: rething this pipe_map.
    pipe_map: List[PipeConditionPipeMap]
    default_pipe_code: Optional[str] = None
    add_alias_from_expression_to: Optional[str] = None

    #########################################################################################
    # Validation
    #########################################################################################
    @override
    def validate_output(self):
        """
        Validate the output for the pipe condition.
        The output of the pipe condition should match the output of all the conditional pipes, and the default pipe.
        """
        for pipe_condition_pipe_map in self.pipe_map:
            pipe = get_required_pipe(pipe_code=pipe_condition_pipe_map.pipe_code)
            if self.output.concept_string != pipe.output.concept_string:
                raise PipeConditionError(
                    f"The output concept code '{self.output.concept_string}' of the pipe '{self.code}' is "
                    f"not matching the output concept code '{pipe.output.concept_string}' of the pipe '{pipe_condition_pipe_map.pipe_code}'"
                )
        if self.default_pipe_code:
            default_pipe = get_required_pipe(pipe_code=self.default_pipe_code)
            if self.output.concept_string != default_pipe.output.concept_string:
                raise PipeConditionError(
                    f"The output concept code '{self.output.concept_string}' of the pipe '{self.code}' is "
                    f"not matching the output concept code '{default_pipe.output.concept_string}' of the default pipe '{self.default_pipe_code}'"
                )

    @field_validator("pipe_map")
    @classmethod
    def validate_pipe_map(cls, pipe_map: List[PipeConditionPipeMap]) -> List[PipeConditionPipeMap]:
        # Validate that the expressions and pipe_code are UNIQUE
        expression_results = [pipe_condition_pipe_map.expression_result for pipe_condition_pipe_map in pipe_map]
        pipe_codes = [pipe_condition_pipe_map.pipe_code for pipe_condition_pipe_map in pipe_map]
        if len(expression_results) != len(set(expression_results)):
            raise PipeDefinitionError(
                f"PipeCondition '{cls.code}' must have a unique expression result for each pipe in pipe_map in pipe_map: {pipe_map}"
            )
        if len(pipe_codes) != len(set(pipe_codes)):
            raise PipeDefinitionError(
                f"PipeCondition '{cls.code}' must have a unique pipe code for each expression result in pipe_map in pipe_map: {pipe_map}"
            )
        return pipe_map

    @model_validator(mode="after")
    def validate_expression(self) -> Self:
        if not has_exactly_one_among_attributes_from_list(self, attributes_list=["expression_template", "expression"]):
            raise PipeDefinitionError("PipeCondition should have exactly one of expression_template or expression")
        return self

    def _make_pipe_condition_details(self, evaluated_expression: str, chosen_pipe_code: str) -> PipeConditionDetails:
        return PipeConditionDetails(
            code=shortuuid.uuid()[:5],
            test_expression=self.expression or self.applied_expression_template,
            pipe_map=self.pipe_map,
            default_pipe_code=self.default_pipe_code,
            evaluated_expression=evaluated_expression,
            chosen_pipe_code=chosen_pipe_code,
        )

    @property
    def applied_expression_template(self) -> str:
        if self.expression_template:
            return self.expression_template
        elif self.expression:
            return "{{ " + self.expression + " }}"
        else:
            raise PipeExecutionError("No expression or expression_template provided")

    #########################################################################################
    # Inputs
    #########################################################################################

    @override
    def required_variables(self) -> Set[str]:
        required_variables: Set[str] = set()
        # Variables from the expression/expression_template
        pipe_jinja2 = PipeJinja2Factory.make_pipe_jinja2_from_template_str(
            domain=self.domain,
            template_str=self.applied_expression_template,
            inputs=self.inputs,
        )
        required_variables.update(pipe_jinja2.required_variables())

        # Variables from the pipe_map
        for pipe_code in self.pipe_dependencies():
            required_variables.update(get_required_pipe(pipe_code=pipe_code).required_variables())
        return required_variables

    def _validate_required_variables(self) -> Self:
        for required_variable_name in self.required_variables():
            if required_variable_name not in self.inputs.variables:
                raise PipeDefinitionError(f"Required variable '{required_variable_name}' is not in the inputs of pipe {self.code}")
        return self

    @override
    def needed_inputs(self) -> PipeInputSpec:
        """
        Calculate the inputs needed by this PipeCondition.

        The inputs are:
        1. Inputs needed by the condition expression/expression_template
        2. Inputs needed by ALL possible target pipes (since we don't know which will be chosen)
        """
        needed_inputs = PipeInputSpecFactory.make_empty()

        # 1. Add the variables from the expression/expression_template
        pipe_jinja2 = PipeJinja2Factory.make_pipe_jinja2_from_template_str(
            domain=self.domain,
            template_str=self.applied_expression_template,
            inputs=self.inputs,
        )

        for var_name in pipe_jinja2.required_variables():
            if not var_name.startswith("_"):  # exclude internal variables starting with `_`
                # We don't know the concept code from just the variable name,
                # so we'll use a generic placeholder that will be validated later
                needed_inputs.add_requirement(
                    variable_name=var_name,
                    concept=ConceptFactory.make_native_concept(
                        native_concept_data=NATIVE_CONCEPTS_DATA[NativeConceptEnum.ANYTHING],
                    ),
                )

        # 2. Add the inputs needed by all possible target pipes
        for pipe_condition_pipe_map in self.pipe_map:
            pipe = get_required_pipe(pipe_code=pipe_condition_pipe_map.pipe_code)
            for input_name, requirement in pipe.needed_inputs().items:
                needed_inputs.add_requirement(variable_name=input_name, concept=requirement.concept)

        return needed_inputs

    @model_validator(mode="after")
    def validate_inputs(self) -> Self:
        if not self.pipe_map:
            raise ValueError(f"Pipe'{self.code}'(PipeCondition) must have at least one mapping in pipe_map")

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
        for named_input_requirement in the_needed_inputs.named_input_requirements:
            if named_input_requirement.variable_name not in self.inputs.variables:
                missing_input_var_error = StaticValidationError(
                    error_type=StaticValidationErrorType.MISSING_INPUT_VARIABLE,
                    domain=self.domain,
                    pipe_code=self.code,
                    variable_names=[named_input_requirement.variable_name],
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
                    domain=self.domain,
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
        self._validate_required_variables()

    @override
    def pipe_dependencies(self) -> Set[str]:
        pipe_codes = [pipe_condition_pipe_map.pipe_code for pipe_condition_pipe_map in self.pipe_map]
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
        log.dev(f"{self.class_name} generating a '{self.output.code}'")

        # TODO: restore pipe_layer feature
        # pipe_run_params.push_pipe_code(pipe_code=pipe_code)

        # Convert PipeInputSpec to blueprint format
        inputs_blueprint: Dict[str, Union[str, InputRequirementBlueprint]] = {}
        for var_name, requirement in self.inputs.root.items():
            inputs_blueprint[var_name] = InputRequirementBlueprint(
                concept=requirement.concept.concept_string,
                multiplicity=requirement.multiplicity,
            )

        pipe_jinja2_blueprint = PipeJinja2Blueprint(
            definition="Jinja2 template for pipe condition evaluation",
            jinja2=self.applied_expression_template,
            inputs=inputs_blueprint,
            output=self.output.code,
        )

        # TODO: use jinja2 directly without going though a pipe
        pipe_jinja2 = PipeJinja2Factory.make_from_blueprint(
            domain=self.domain,
            pipe_code="adhoc_for_pipe_condition",
            blueprint=pipe_jinja2_blueprint,
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

        chosen_pipe_code = next(
            (
                pipe_condition_pipe_map.pipe_code
                for pipe_condition_pipe_map in self.pipe_map
                if pipe_condition_pipe_map.expression_result == evaluated_expression
            ),
            self.default_pipe_code,
        )
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
        log.debug(f"PipeCondition: dry run controller pipe: {self.code}")

        # 1. Validate that all required inputs are present in the working memory
        needed_inputs = self.needed_inputs()
        missing_input_names: List[str] = []

        for named_input_requirement in needed_inputs.named_input_requirements:
            if not working_memory.get_optional_stuff(named_input_requirement.variable_name):
                missing_input_names.append(named_input_requirement.variable_name)

        if missing_input_names:
            log.error(f"Dry run failed: missing required inputs: {missing_input_names}")
            raise DryRunError(
                message=f"Dry run failed for pipe '{self.code}' (PipeCondition): missing required inputs: {', '.join(missing_input_names)}",
                missing_inputs=missing_input_names,
                pipe_code=self.code,
            )

        # 2. Validate that the expression template is valid
        try:
            pipe_jinja2 = PipeJinja2Factory.make_pipe_jinja2_from_template_str(
                domain=self.domain,
                template_str=self.applied_expression_template,
                inputs=self.inputs,
            )
            # Get required variables to validate the template syntax
            required_variables = pipe_jinja2.required_variables()
            log.debug(f"Expression template is valid, requires variables: {required_variables}")
        except Exception as exc:
            log.error(f"Dry run failed: invalid expression template: {exc}")
            error_msg = (
                f"Dry run failed for pipe '{self.code}' (PipeCondition): invalid expression template '{self.applied_expression_template}': {exc}"
            )
            raise DryRunError(
                message=error_msg,
                missing_inputs=[],
                pipe_code=self.code,
            )

        # 3. Validate that all pipes in the pipe_map exist
        all_pipe_codes = set([pipe_condition_pipe_map.pipe_code for pipe_condition_pipe_map in self.pipe_map])
        if self.default_pipe_code:
            all_pipe_codes.add(self.default_pipe_code)

        missing_pipes: List[str] = []
        for pipe_code in all_pipe_codes:
            try:
                get_required_pipe(pipe_code=pipe_code)
                log.debug(f"Pipe '{pipe_code}' exists and is accessible")
            except Exception as exc:
                log.error(f"Dry run failed: pipe '{pipe_code}' not found: {exc}")
                missing_pipes.append(pipe_code)

        if missing_pipes:
            error_msg = (
                f"Dry run failed for pipe '{self.code}' (PipeCondition): missing pipes: {', '.join(missing_pipes)}. "
                f"Pipe map: {self.pipe_map}, default: {self.default_pipe_code}"
            )
            raise DryRunError(
                message=error_msg,
                missing_inputs=[],
                pipe_code=self.code,
            )

        # Here, it should launch the dry run of all the pipes in the pipe_map
        for pipe_condition_pipe_map in self.pipe_map:
            pipe_code = pipe_condition_pipe_map.pipe_code
            pipe = get_required_pipe(pipe_code=pipe_code)
            await pipe.run_pipe(
                job_metadata=job_metadata,
                working_memory=working_memory,
                pipe_run_params=pipe_run_params,
            )
        return PipeOutput(working_memory=working_memory)
