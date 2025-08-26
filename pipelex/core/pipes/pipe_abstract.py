from abc import ABC, abstractmethod
from typing import List, Optional, Set, Type

from pydantic import BaseModel, ConfigDict, Field, field_validator

from pipelex.core.concepts.concept import Concept
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.pipes.pipe_blueprint import PipeBlueprint
from pipelex.core.pipes.pipe_input_spec import PipeInputSpec
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.core.pipes.pipe_run_params import PipeRunParams
from pipelex.exceptions import PipeStackOverflowError
from pipelex.pipeline.job_metadata import JobMetadata


class PipeAbstract(ABC, BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    code: str
    domain: str
    definition: Optional[str] = None
    inputs: PipeInputSpec = Field(default_factory=PipeInputSpec)
    output: Concept

    @field_validator("code", mode="before")
    def validate_pipe_code_syntax(cls, code: str) -> str:
        PipeBlueprint.validate_pipe_code_syntax(pipe_code=code)
        return code

    @abstractmethod
    def validate_output(self):
        """
        Validate the output for the pipe.
        """
        pass

    @property
    def class_name(self) -> str:
        return self.__class__.__name__

    def validate_with_libraries(self):
        """
        Validate the pipe with the libraries, after the static validation
        """
        pass

    @abstractmethod
    def required_variables(self) -> Set[str]:
        """
        Return the variables that are required for the pipe to run.
        The required variables are only the list:
        # 1 - The inputs of dependency pipes
        # 2 - The variables in the pipe definition
            - PipeConditon : Variables in the expression
            - PipeBatch : Variables in the batch_params
            - PipeLLM : Variables in the prompt
        """
        pass

    @abstractmethod
    def needed_inputs(self) -> PipeInputSpec:
        """
        Return the inputs that are needed for the pipe to run. (Mostly the inputs of the pipe themselves)
        """
        pass

    def pipe_dependencies(self) -> Set[str]:
        """
        Return the pipes that are dependencies of the pipe.
            - PipeBatch : The pipe that is being batched
            - PipeCondition : The pipes in the pipe_map
            - PipeSequence : The pipes in the steps
        """
        return set()

    def concept_dependencies(self) -> List[Concept]:
        required_concepts: List[Concept] = [self.output]
        for concept in self.inputs.concepts:
            required_concepts.append(concept)
        required_concepts.append(self.output)
        return required_concepts

    @abstractmethod
    async def run_pipe(
        self,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: Optional[str] = None,
    ) -> PipeOutput:
        pass

    def monitor_pipe_stack(self, pipe_run_params: PipeRunParams):
        pipe_stack = pipe_run_params.pipe_stack
        limit = pipe_run_params.pipe_stack_limit
        if len(pipe_stack) > limit:
            raise PipeStackOverflowError(f"Exceeded pipe stack limit of {limit}. You can raise that limit in the config. Stack:\n{pipe_stack}")


PipeAbstractType = Type[PipeAbstract]
