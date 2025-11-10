from abc import ABC, abstractmethod
from typing import Any, final

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from pipelex import log
from pipelex.cogt.exceptions import ModelChoiceNotFoundError
from pipelex.core.concepts.concept import Concept
from pipelex.core.memory.exceptions import WorkingMemoryStuffNotFoundError
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.pipes.exceptions import PipeOperatorModelChoiceError, PipeRunInputsError
from pipelex.core.pipes.input_requirements import InputRequirements
from pipelex.core.pipes.pipe_blueprint import PipeBlueprint
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipe_run.pipe_run_params import PipeRunParams
from pipelex.pipeline.exceptions import PipeStackOverflowError
from pipelex.pipeline.job_metadata import JobMetadata
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
        PipeBlueprint.validate_pipe_code_syntax(pipe_code=code)
        return code

    @model_validator(mode="after")
    def validate_pipe(self) -> Self:
        self.validate_input_static()
        self.validate_output_static()
        return self

    @abstractmethod
    def validate_input_with_library(self, library_id: str):
        """Validate the inputs for the pipe with the library."""

    @abstractmethod
    def validate_input_static(self):
        """Validate the inputs for the pipe."""

    @abstractmethod
    def validate_output_with_library(self, library_id: str):
        """Validate the output for the pipe with the library."""

    @abstractmethod
    def validate_output_static(self):
        """Validate the output for the pipe."""

    @final
    def validate_with_libraries(self, library_id: str):
        """Validate the pipe with the libraries, after the static validation"""
        try:
            self.validate_input_with_library(library_id=library_id)
            self.validate_output_with_library(library_id=library_id)
        except ModelChoiceNotFoundError as exc:
            raise PipeOperatorModelChoiceError(
                message=exc.message,
                pipe_type=self.pipe_type,
                pipe_code=self.code,
                model_type=exc.model_type,
                model_choice=exc.model_choice,
            ) from exc

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
                working_memory.get_stuff(required_stuff_name)
            except WorkingMemoryStuffNotFoundError as exc:
                variable_name: str = exc.variable_name or required_stuff_name
                missing_inputs[variable_name] = exc.concept_code or requirement.concept.code
        if missing_inputs:
            raise PipeRunInputsError(
                message=f"Missing required inputs for pipe '{self.code}': {missing_inputs}", pipe_code=self.code, missing_inputs=missing_inputs
            )

        pipe_run_info = self._format_pipe_run_info(pipe_run_params=pipe_run_params)
        log.info(pipe_run_info)

        pipe_output = await self._run_pipe(
            job_metadata=job_metadata, working_memory=working_memory, pipe_run_params=pipe_run_params, output_name=output_name
        )

        pipe_run_params.pop_pipe_from_stack(pipe_code=self.code)
        return pipe_output


PipeAbstractType = type[PipeAbstract]
