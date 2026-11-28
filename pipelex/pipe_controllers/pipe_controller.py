from abc import abstractmethod
from typing import TYPE_CHECKING, Any, Literal, final

from typing_extensions import override

from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.kernel.stored_value_ops import load_stored_values_through_leaf
from pipelex.pipe_machinery.pipe_abstract import PipeAbstract
from pipelex.pipe_run.pipe_run_params import PipeRunParams
from pipelex.system.job_metadata import JobMetadata

if TYPE_CHECKING:
    from pipelex.libraries.library_crate import LibraryCrate


class PipeController(PipeAbstract):
    pipe_category: Literal["PipeController"] = "PipeController"

    @property
    def class_name(self) -> str:
        return self.__class__.__name__

    @override
    async def _load_stored_input_values(self, *, roots: dict[str, Any], job_metadata: JobMetadata, pipe_run_params: PipeRunParams) -> None:
        await load_stored_values_through_leaf(
            roots=roots, read_paths=None, job_metadata=job_metadata, cogt_run_params=pipe_run_params.cogt_run_params
        )

    @override
    @abstractmethod
    def pipe_dependencies(self) -> set[str]:
        """Return the pipes that are dependencies of the pipe.
        - PipeBatch: The pipe that is being batched
        - PipeCondition: The pipes in the outcome_map
        - PipeSequence: The pipes in the steps
        """

    @final
    @override
    async def _live_run_pipe(
        self,
        *,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: str | None = None,
        library_crate: "LibraryCrate | None" = None,
    ) -> PipeOutput:
        return await self._live_run_controller_pipe(
            job_metadata=job_metadata,
            working_memory=working_memory,
            pipe_run_params=pipe_run_params,
            output_name=output_name,
            library_crate=library_crate,
        )

    @final
    @override
    async def _dry_run_pipe(
        self,
        *,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: str | None = None,
        library_crate: "LibraryCrate | None" = None,
    ) -> PipeOutput:
        return await self._dry_run_controller_pipe(
            job_metadata=job_metadata,
            working_memory=working_memory,
            pipe_run_params=pipe_run_params,
            output_name=output_name,
            library_crate=library_crate,
        )

    @abstractmethod
    async def _live_run_controller_pipe(
        self,
        *,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: str | None = None,
        library_crate: "LibraryCrate | None" = None,
    ) -> PipeOutput:
        pass

    @abstractmethod
    async def _dry_run_controller_pipe(
        self,
        *,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: str | None = None,
        library_crate: "LibraryCrate | None" = None,
    ) -> PipeOutput:
        pass
