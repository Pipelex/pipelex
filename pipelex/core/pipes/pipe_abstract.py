from abc import ABC, abstractmethod
from typing import Any, final

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from pipelex import log
from pipelex.cogt.exceptions import ModelChoiceNotFoundError
from pipelex.core.bundles.exceptions import PipeValidationErrorType
from pipelex.core.concepts.concept import Concept
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.exceptions import PipeValidationError
from pipelex.core.memory.exceptions import WorkingMemoryStuffNotFoundError
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.pipe_errors import PipeDefinitionError
from pipelex.core.pipes.exceptions import PipeAbstractValueError, PipeRunInputsError
from pipelex.core.pipes.input_requirements import InputRequirements
from pipelex.core.pipes.pipe_blueprint import AllowedPipeCategories, AllowedPipeTypes
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipe_run.pipe_run_params import PipeRunParams
from pipelex.pipeline.exceptions import PipeStackOverflowError
from pipelex.pipeline.job_metadata import JobMetadata
from pipelex.tools.misc.string_utils import is_snake_case
from pipelex.types import Self


class PipeAbstract(ABC, BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    pipe_category: Any  # Any so that subclasses can put a Literal
    type: Any  # Any so that subclasses can put a Literal
    code: str
    domain: str
    description: str | None = None
    inputs: InputRequirements = Field(default_factory=InputRequirements)
    output: Concept

    @property
    def pipe_type(self) -> str:
        return self.__class__.__name__

    @field_validator("code", mode="before")
    @classmethod
    def validate_pipe_code_syntax(cls, code: str) -> str:
        if not is_snake_case(code):
            msg = f"Invalid pipe code syntax '{code}'. Must be in snake_case."
            raise PipeDefinitionError(msg)
        return code

    @field_validator("type", mode="after")
    @classmethod
    def validate_pipe_type(cls, value: Any) -> Any:
        if value not in AllowedPipeTypes.value_list():
            msg = f"Invalid pipe type '{value}' for pipe '{cls.code}'. Must be one of: {AllowedPipeTypes.value_list()}"
            raise ValueError(msg)
        return value

    @field_validator("pipe_category", mode="after")
    @classmethod
    def validate_pipe_category(cls, value: Any) -> Any:
        if value not in AllowedPipeCategories.value_list():
            msg = f"Invalid pipe category '{value}' for pipe '{cls.code}'. Must be one of: {AllowedPipeCategories.value_list()}"
            raise ValueError(msg)
        return value

    @model_validator(mode="after")
    def validate_pipe_category_based_on_type(self) -> Self:
        if self.pipe_category != AllowedPipeTypes(self.type).category:
            msg = f"Invalid pipe category '{self.pipe_category}' for pipe '{self.code}'. Must be one of: {self.type.category}"
            raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def validate_pipe(self) -> Self:
        self.generic_validate_input_static()
        self.generic_validate_output_static()
        return self

    @final
    def validate_with_libraries(self):
        try:
            self.generic_validate_input_with_library()
            self.generic_validate_output_with_library()
        except ModelChoiceNotFoundError as exc:
            msg = f"Model choice not found for pipe '{self.code}': {exc}"
            raise PipeAbstractValueError(msg) from exc

    @final
    def generic_validate_input_static(self):
        # Put here the validation that is common to all pipes
        # ...

        # Now apply custom validation for pipes
        self.validate_input_static()

    @final
    def generic_validate_output_static(self):
        # Put here the validation that is common to all pipes
        # ...
        # Now apply custom validation for pipes
        self.validate_output_static()

    @final
    def generic_validate_input_with_library(self):
        # First validate required variables are in the inputs
        for required_variable_name in self.required_variables():
            if required_variable_name not in self.inputs.variables:
                raise PipeValidationError(
                    error_type=PipeValidationErrorType.MISSING_INPUT_VARIABLE,
                    domain=self.domain,
                    pipe_code=self.code,
                    variable_names=[required_variable_name],
                    explanation=(
                        f"Required variable '{required_variable_name}' is not in the inputs of pipe '{self.code}'. Current inputs: {self.inputs}"
                    ),
                )

        # Then validate that all inputs are actually needed and match requirements exactly
        the_needed_inputs = self.needed_inputs()

        # Check all required variables are in the inputs and match the required InputRequirement
        for named_input_requirement in the_needed_inputs.named_input_requirements:
            var_name = named_input_requirement.variable_name

            if var_name not in self.inputs.variables:
                raise PipeValidationError(
                    error_type=PipeValidationErrorType.MISSING_INPUT_VARIABLE,
                    domain=self.domain,
                    pipe_code=self.code,
                    variable_names=[var_name],
                    explanation=(f"Required variable '{var_name}' is not in the inputs of pipe '{self.code}'. Current inputs: {self.inputs}"),
                )

            # Compare the essential parts of InputRequirement (concept code + multiplicity)
            # Skip validation if the needed requirement is Dynamic or Anything (flexible output types)
            declared_requirement = self.inputs.root[var_name]
            needed_requirement = the_needed_inputs.root[named_input_requirement.requirement_expression or var_name]

            # Allow mismatch if the needed requirement is a flexible type (Dynamic or Anything)
            if (
                needed_requirement.concept.code not in (NativeConceptCode.DYNAMIC, NativeConceptCode.ANYTHING)
                and declared_requirement != needed_requirement
            ):
                raise PipeValidationError(
                    error_type=PipeValidationErrorType.INPUT_REQUIREMENT_MISMATCH,
                    domain=self.domain,
                    pipe_code=self.code,
                    variable_names=[var_name],
                    explanation=(
                        f"Input variable '{var_name}' requirement mismatch in pipe '{self.code}'.\n"
                        f"Declared: input requirement {declared_requirement}.\n"
                        f"Required: input requirement {needed_requirement}"
                    ),
                )

        # Check that all declared inputs are actually needed
        for input_name in self.inputs.variables:
            if input_name not in the_needed_inputs.required_names:
                raise PipeValidationError(
                    error_type=PipeValidationErrorType.EXTRANEOUS_INPUT_VARIABLE,
                    domain=self.domain,
                    pipe_code=self.code,
                    variable_names=[input_name],
                    explanation=f"Extraneous input '{input_name}' found in the inputs of pipe {self.code}",
                )

        # Now apply custom validation for pipes
        self.validate_input_with_library()

    @final
    def generic_validate_output_with_library(self):
        # Put here the validation that is common to all pipes
        # ...

        # Now apply custom validation for pipes
        self.validate_output_with_library()

    @abstractmethod
    def validate_input_with_library(self):
        pass

    @abstractmethod
    def validate_input_static(self):
        pass

    @abstractmethod
    def validate_output_with_library(self):
        pass

    @abstractmethod
    def validate_output_static(self):
        pass

    def validate_before_run(
        self,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: str | None = None,
    ): ...

    def validate_after_run(
        self,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: str | None = None,
    ): ...

    @abstractmethod
    def required_variables(self) -> set[str]:
        """Return the variables that are required for the pipe to run.
        The required variables are only the list:
        # 1 - The inputs of dependency pipes
        # 2 - The variables in the pipe definition
            - PipeConditon : Variables in the expression
            - PipeBatch: Variables in the batch_params
            - PipeLLM : Variables in the prompt
        """

    @abstractmethod
    def needed_inputs(self, visited_pipes: set[str] | None = None) -> InputRequirements:
        """Return the inputs that are needed for the pipe to run.

        Args:
            visited_pipes: Set of pipe codes currently being processed to prevent infinite recursion.
                          If None, starts recursion detection with an empty set.

        Returns:
            InputRequirements containing all needed inputs for this pipe

        """

    def monitor_pipe_stack(self, pipe_run_params: PipeRunParams):
        pipe_stack = pipe_run_params.pipe_stack
        limit = pipe_run_params.pipe_stack_limit
        if len(pipe_stack) > limit:
            msg = f"Exceeded pipe stack limit of {limit}. You can raise that limit in the config. Stack:\n{pipe_stack}"
            raise PipeStackOverflowError(message=msg, limit=limit, pipe_stack=pipe_stack)

    def _format_pipe_run_info(self, pipe_run_params: PipeRunParams) -> str:
        indent_level = len(pipe_run_params.pipe_stack) - 1
        indent = "   " * indent_level
        if indent_level > 0:
            indent = f"{indent}[yellow]↳[/yellow] "
        pipe_type_label = f"[white]{self.pipe_type}:[/white]"
        match pipe_run_params.run_mode:
            case PipeRunMode.LIVE:
                pass
            case PipeRunMode.DRY:
                pipe_type_label = f"[dim]Dry run:[/dim] {pipe_type_label}"
        pipe_code_label = f"[red]{self.code}[/red]"
        concept_code_label = f"[bold green]{self.output.code}[/bold green]"
        arrow = "[yellow]→[/yellow]"
        return f"{indent}{pipe_type_label} {pipe_code_label} {arrow} {concept_code_label}"

    @abstractmethod
    async def _run_pipe(
        self,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: str | None = None,
    ) -> PipeOutput:
        pass

    @final
    async def run_pipe(
        self,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: str | None = None,
    ) -> PipeOutput:
        pipe_run_params.push_pipe_to_stack(pipe_code=self.code)
        self.monitor_pipe_stack(pipe_run_params=pipe_run_params)

        updated_metadata = JobMetadata(
            pipe_job_ids=[self.code],
        )
        job_metadata.update(updated_metadata=updated_metadata)

        # check we have the required inputs in the working memory
        missing_inputs: dict[str, str] = {}
        for required_stuff_name, requirement in self.needed_inputs().items:
            try:
                if not working_memory.is_stuff_exists(name=required_stuff_name):
                    missing_inputs[required_stuff_name] = requirement.concept.code
            except WorkingMemoryStuffNotFoundError as exc:
                variable_name: str = exc.variable_name or required_stuff_name
                missing_inputs[variable_name] = exc.concept_code or requirement.concept.code
        if missing_inputs:
            raise PipeRunInputsError(
                message=f"Missing required inputs for pipe '{self.code}': {missing_inputs}", pipe_code=self.code, missing_inputs=missing_inputs
            )

        pipe_run_info = self._format_pipe_run_info(pipe_run_params=pipe_run_params)
        if pipe_run_params.run_mode == PipeRunMode.LIVE:
            log.info(pipe_run_info)

        self.validate_before_run(job_metadata=job_metadata, working_memory=working_memory, pipe_run_params=pipe_run_params, output_name=output_name)

        pipe_output = await self._run_pipe(
            job_metadata=job_metadata, working_memory=working_memory, pipe_run_params=pipe_run_params, output_name=output_name
        )

        self.validate_after_run(job_metadata=job_metadata, working_memory=working_memory, pipe_run_params=pipe_run_params, output_name=output_name)

        pipe_run_params.pop_pipe_from_stack(pipe_code=self.code)
        return pipe_output


PipeAbstractType = type[PipeAbstract]
