from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from pipelex.core.concepts.concept import Concept
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.pipes.input_requirements import InputRequirements
from pipelex.core.pipes.pipe_blueprint import PipeBlueprint
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.exceptions import PipeStackOverflowError
from pipelex.pipe_run.pipe_run_params import PipeRunParams
from pipelex.pipeline.job_metadata import JobMetadata


class PipeAbstract(ABC, BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    pipe_category: Any  # Any so that subclasses can put a Literal
    type: Any  # Any so that subclasses can put a Literal
    code: str
    domain: str
    description: str | None = None
    inputs: InputRequirements = Field(default_factory=InputRequirements)
    output: Concept

    @field_validator("code", mode="before")
    @classmethod
    def validate_pipe_code_syntax(cls, code: str) -> str:
        PipeBlueprint.validate_pipe_code_syntax(pipe_code=code)
        return code

    @abstractmethod
    def validate_output(self):
        """Validate the output for the pipe."""

    def validate_with_libraries(self):
        """Validate the pipe with the libraries, after the static validation"""

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
            PipeInput containing all needed inputs for this pipe

        """

    def pipe_dependencies(self) -> set[str]:
        """Return the pipes that are dependencies of the pipe.
        - PipeBatch: The pipe that is being batched
        - PipeCondition: The pipes in the outcome_map
        - PipeSequence: The pipes in the steps
        """
        return set()

    def concept_dependencies(self) -> list[Concept]:
        required_concepts: list[Concept] = [self.output]
        required_concepts.extend(self.inputs.concepts)
        required_concepts.append(self.output)
        return required_concepts

    @abstractmethod
    async def run_pipe(
        self,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: str | None = None,
        print_intermediate_outputs: bool | None = False,
    ) -> PipeOutput:
        pass

    def monitor_pipe_stack(self, pipe_run_params: PipeRunParams):
        pipe_stack = pipe_run_params.pipe_stack
        limit = pipe_run_params.pipe_stack_limit
        if len(pipe_stack) > limit:
            msg = f"Exceeded pipe stack limit of {limit}. You can raise that limit in the config. Stack:\n{pipe_stack}"
            raise PipeStackOverflowError(msg)


PipeAbstractType = type[PipeAbstract]
