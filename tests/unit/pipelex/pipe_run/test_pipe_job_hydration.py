from typing import TYPE_CHECKING, cast

import pytest

from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.libraries.library_crate import LibraryCrate
from pipelex.pipe_run.exceptions import PipeJobError
from pipelex.pipe_run.pipe_job import PipeJob
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.pipeline.job_metadata import JobMetadata

if TYPE_CHECKING:
    from pipelex.core.pipes.pipe_abstract import PipeAbstract


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
        job_metadata=JobMetadata(user_id="test-user", pipeline_run_id="test-run"),
        output_name=None,
        library_crate=library_crate,
    )


def _make_dummy_crate() -> LibraryCrate:
    """Build a minimal LibraryCrate for testing."""
    return LibraryCrate(concepts={}, pipes={}, domains={}, source_map={})


class TestPipeJobHydration:
    def test_prepare_for_temporal_moves_wm_to_raw(self) -> None:
        """When library_crate is present, prepare_for_temporal() returns a copy with WM serialized to raw."""
        working_memory = WorkingMemory()
        crate = _make_dummy_crate()
        pipe_job = _make_pipe_job(working_memory=working_memory, library_crate=crate)

        result = pipe_job.prepare_for_temporal()

        assert result.working_memory is None
        assert result.working_memory_raw is not None
        assert isinstance(result.working_memory_raw, dict)

    def test_prepare_for_temporal_noop_without_crate(self) -> None:
        """Without library_crate, prepare_for_temporal() returns self unchanged."""
        working_memory = WorkingMemory()
        pipe_job = _make_pipe_job(working_memory=working_memory, library_crate=None)

        result = pipe_job.prepare_for_temporal()

        assert result is pipe_job
        assert result.working_memory is working_memory
        assert result.working_memory_raw is None

    def test_prepare_for_temporal_empty_wm(self) -> None:
        """Empty WorkingMemory serializes to a dict with empty root."""
        working_memory = WorkingMemory()
        crate = _make_dummy_crate()
        pipe_job = _make_pipe_job(working_memory=working_memory, library_crate=crate)

        result = pipe_job.prepare_for_temporal()

        assert result.working_memory_raw is not None
        assert result.working_memory_raw["root"] == {}

    def test_prepare_for_temporal_does_not_mutate_original(self) -> None:
        """prepare_for_temporal() leaves the original PipeJob unchanged."""
        working_memory = WorkingMemory()
        crate = _make_dummy_crate()
        pipe_job = _make_pipe_job(working_memory=working_memory, library_crate=crate)

        _ = pipe_job.prepare_for_temporal()

        assert pipe_job.working_memory is working_memory
        assert pipe_job.working_memory_raw is None

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

    def test_prepare_for_temporal_crate_without_wm(self) -> None:
        """library_crate present but working_memory is None returns self unchanged."""
        crate = _make_dummy_crate()
        pipe_job = _make_pipe_job(working_memory=None, library_crate=crate)

        result = pipe_job.prepare_for_temporal()

        assert result is pipe_job
        assert result.working_memory is None
        assert result.working_memory_raw is None
