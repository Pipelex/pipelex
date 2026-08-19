from typing import TYPE_CHECKING, cast

import pytest

from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.libraries.library_crate import LibraryCrate
from pipelex.pipe_run.exceptions import PipeJobError
from pipelex.pipe_run.pipe_job import PipeJob
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.system.job_metadata import JobMetadata

if TYPE_CHECKING:
    from pipelex.pipe_machinery.pipe_abstract import PipeAbstract


def _make_pipe_job(
    working_memory: WorkingMemory | None = None,
    library_crate: LibraryCrate | None = None,
) -> PipeJob:
    """Build a PipeJob using model_construct to bypass pipe validation (we're testing PipeJob methods, not pipe)."""
    return PipeJob.model_construct(
        pipe=cast("PipeAbstract", None),
        working_memory=working_memory,
        working_memory_raw=None,
        pipe_run_params=PipeRunParamsFactory.make_run_params(),
        job_metadata=JobMetadata(storage_scope="test/scope", user_id="test-user", pipeline_run_id="test-run"),
        output_name=None,
        library_crate=library_crate,
    )


class TestPipeJobHydration:
    def test_get_working_memory_from_typed(self) -> None:
        """get_working_memory() returns the typed WorkingMemory when set."""
        working_memory = WorkingMemory()
        pipe_job = _make_pipe_job(working_memory=working_memory)

        result = pipe_job.get_working_memory()
        assert result is working_memory

    def test_get_working_memory_from_raw_raises(self) -> None:
        """get_working_memory() raises PipeJobError when only raw is set."""
        pipe_job = _make_pipe_job(working_memory=None)
        pipe_job.working_memory_raw = {"root": {}, "aliases": {}}

        with pytest.raises(PipeJobError, match="raw form"):
            pipe_job.get_working_memory()

    def test_get_working_memory_both_none_returns_empty(self) -> None:
        """get_working_memory() returns empty WorkingMemory when both are None."""
        pipe_job = _make_pipe_job(working_memory=None)

        result = pipe_job.get_working_memory()
        assert isinstance(result, WorkingMemory)
        assert len(result.root) == 0
