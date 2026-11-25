from typing import Any

from pydantic import BaseModel, PrivateAttr

from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.pipes.declared_item_count_scope import DryRunMockTally
from pipelex.libraries.library_crate import LibraryCrate
from pipelex.pipe_machinery.pipe_abstract import PipeAbstract
from pipelex.pipe_run.exceptions import PipeJobError
from pipelex.pipe_run.pipe_run_params import PipeRunParams
from pipelex.system.job_metadata import JobMetadata


class PipeJob(BaseModel):
    pipe: PipeAbstract
    working_memory: WorkingMemory | None = None
    working_memory_raw: dict[str, Any] | None = None
    pipe_run_params: PipeRunParams
    job_metadata: JobMetadata
    output_name: str | None = None
    library_crate: LibraryCrate | None = None
    # The budget of mock items the run's setup opened, when it built mock inputs or ran dry, carried to the run so its
    # pipes spend the same budget (`PipeRouterProtocol.run`). It belongs to this process: it is never serialized, so a
    # job crossing to a worker leaves it behind, and the worker's activities count against budgets of their own.
    _dry_run_mock_tally: DryRunMockTally | None = PrivateAttr(default=None)

    @property
    def dry_run_mock_tally(self) -> DryRunMockTally | None:
        """The budget of mock items the run's setup opened in this process, which the run's pipes spend too."""
        return self._dry_run_mock_tally

    def carry_dry_run_mock_tally(self, *, tally: DryRunMockTally) -> None:
        """Carry the budget of mock items the run's setup opened to the run, so the setup and the run spend one budget."""
        self._dry_run_mock_tally = tally

    @property
    def pipe_type(self) -> str:
        return self.pipe.__class__.__name__

    def get_working_memory(self) -> WorkingMemory:
        if self.working_memory is not None:
            return self.working_memory
        if self.working_memory_raw is not None:
            msg = "WorkingMemory is in raw form and has not been hydrated yet"
            raise PipeJobError(msg)
        return WorkingMemory()
