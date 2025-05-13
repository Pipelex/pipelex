# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from abc import ABC, abstractmethod
from functools import wraps
from typing import Any, Awaitable, Callable, Coroutine, Optional, ParamSpec, Set, Type, TypeVar

from pydantic import BaseModel, ConfigDict

from pipelex.core.pipe_output import PipeOutput
from pipelex.core.pipe_run_params import PipeRunParams
from pipelex.core.working_memory import WorkingMemory
from pipelex.job_metadata import JobMetadata

F = TypeVar("F", bound=Callable[..., Awaitable[Any]])
P = ParamSpec("P")
R = TypeVar("R")


def update_job_metadata_for_pipe(
    func: Callable[P, Coroutine[Any, Any, R]],
) -> Callable[P, Coroutine[Any, Any, R]]:
    @wraps(func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        pipe_code = kwargs.get("pipe_code")
        if pipe_code is None:
            raise RuntimeError("pipe_code argument is required for this decorated function.")
        if not isinstance(pipe_code, str):
            raise TypeError("The pipe_code argument must be of type str.")

        job_metadata = kwargs.get("job_metadata")
        if job_metadata is None:
            raise RuntimeError("job_metadata argument is required for this decorated function.")
        if not isinstance(job_metadata, JobMetadata):
            raise TypeError("The job_metadata argument must be of type JobMetadata.")

        updated_metadata = JobMetadata(
            session_id=job_metadata.session_id,
            pipe_job_ids=[pipe_code],
        )
        job_metadata.update(updated_metadata=updated_metadata)

        return await func(*args, **kwargs)

    return wrapper


class PipeAbstract(ABC, BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    code: str = "adhoc_pipe"
    domain: str

    definition: Optional[str] = None
    input_concept_code: Optional[str] = None
    output_concept_code: str

    def pipe_dependencies(self) -> Set[str]:
        return set()

    def concept_dependencies(self) -> Set[str]:
        required_concepts = set([self.output_concept_code])
        if self.input_concept_code:
            required_concepts.add(self.input_concept_code)
        return required_concepts

    def validate_with_libraries(self):
        pass

    @property
    def required_input_concept_code(self) -> str:
        if self.input_concept_code is None:
            raise RuntimeError("input_concept_code is required")
        return self.input_concept_code

    def required_variables(self) -> Set[str]:
        return set()

    @abstractmethod
    async def run_pipe(
        self,
        pipe_code: str,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: Optional[str] = None,
    ) -> PipeOutput:
        pass

    @property
    def class_name(self) -> str:
        return self.__class__.__name__


PipeAbstractType = Type[PipeAbstract]
