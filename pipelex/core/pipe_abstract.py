from abc import ABC, abstractmethod
from typing import Optional, Set, Type

from pydantic import BaseModel, ConfigDict

from pipelex.core.pipe_output import PipeOutput
from pipelex.core.pipe_run_params import PipeRunParams
from pipelex.core.working_memory import WorkingMemory
from pipelex.exceptions import PipeStackOverflowError
from pipelex.pipeline.job_metadata import JobMetadata


class PipeAbstract(ABC, BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    code: str
    domain: str

    definition: Optional[str] = None
    input_concept_code: Optional[str] = None
    output_concept_code: str

    @property
    def class_name(self) -> str:
        return self.__class__.__name__

    def validate_with_libraries(self):
        pass

    # Dependencies

    def pipe_dependencies(self) -> Set[str]:
        return set()

    def concept_dependencies(self) -> Set[str]:
        required_concepts = set([self.output_concept_code])
        if self.input_concept_code:
            required_concepts.add(self.input_concept_code)
        return required_concepts

    # Required variables

    @property
    def required_input_concept_code(self) -> str:
        if self.input_concept_code is None:
            raise RuntimeError("input_concept_code is required")
        return self.input_concept_code

    def required_variables(self) -> Set[str]:
        return set()

    # Run pipe

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
