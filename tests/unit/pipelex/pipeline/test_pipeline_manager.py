"""Unit tests for ``PipelineManager`` per-run entry lifecycle.

Pins the two-sided contract around explicit ``pipeline_run_id`` reuse:

- Serial resubmission: once a run's entry is removed (the runner's ``finally`` does this
  after every run), re-registering the same ``pipeline_run_id`` succeeds.
- Concurrent duplicate: while a run's entry is registered, ``add_new_pipeline`` with the
  same ``pipeline_run_id`` raises. This raise is load-bearing — it fires before
  ``GraphTracerManager.open_tracer`` is reached in ``pipeline_run_setup``, shielding a
  LIVE direct-mode tracer (keyed by the caller-suppliable ``pipeline_run_id``) from
  ``open_tracer``'s stale-key pop-and-replace healing. Do not relax it without gating
  that healing to run-unique keys.
"""

import pytest

from pipelex.pipeline.exceptions import PipelineManagerAlreadyExistsError
from pipelex.pipeline.pipeline_manager import PipelineManager


class TestPipelineManagerRemoval:
    def test_remove_then_resubmit_same_run_id_succeeds(self) -> None:
        """Serial resubmission: after removal, the same ``pipeline_run_id`` registers again."""
        manager = PipelineManager()
        manager.add_new_pipeline(pipe_code="some_pipe", pipeline_run_id="run-1")
        manager.remove_pipeline(pipeline_run_id="run-1")
        pipeline = manager.add_new_pipeline(pipe_code="some_pipe", pipeline_run_id="run-1")
        assert pipeline.pipeline_run_id == "run-1"

    def test_remove_is_tolerant_of_absent_key(self) -> None:
        """Removal of an unregistered id is a no-op — the entry may legitimately be absent
        when setup failed before the registration committed.
        """
        manager = PipelineManager()
        manager.remove_pipeline(pipeline_run_id="never-registered")

    def test_remove_only_targets_the_given_run(self) -> None:
        manager = PipelineManager()
        manager.add_new_pipeline(pipe_code="some_pipe", pipeline_run_id="run-1")
        manager.add_new_pipeline(pipe_code="some_pipe", pipeline_run_id="run-2")
        manager.remove_pipeline(pipeline_run_id="run-1")
        assert manager.get_optional_pipeline(pipeline_run_id="run-1") is None
        assert manager.get_optional_pipeline(pipeline_run_id="run-2") is not None

    def test_concurrent_duplicate_still_raises(self) -> None:
        """While the first run's entry is live, the same ``pipeline_run_id`` must collide
        loudly (tracer shield — see module docstring).
        """
        manager = PipelineManager()
        manager.add_new_pipeline(pipe_code="some_pipe", pipeline_run_id="run-1")
        with pytest.raises(PipelineManagerAlreadyExistsError):
            manager.add_new_pipeline(pipe_code="some_pipe", pipeline_run_id="run-1")
