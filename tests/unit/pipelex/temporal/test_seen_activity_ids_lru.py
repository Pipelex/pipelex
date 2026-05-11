"""Unit tests for the LRU-bounded ``_seen_activity_ids`` cache on
``ContentGeneratorInWorkflow``.

The cache prevents unbounded memory growth on long-running workers. Each
entry is one ``(workflow_id, run_id) -> set[str]`` mapping recording the
activity_ids observed during one workflow execution. Eviction is FIFO by
insertion order with LRU refresh on touch.

Replay-safety is unaffected: ``_record_activity_id`` short-circuits on
``workflow.unsafe.is_replaying()``, so the LRU only mutates on first
execution.
"""

import pytest
from pytest_mock import MockerFixture

from pipelex.cogt.content_generation.generated_content_factory import GeneratedContentFactory
from pipelex.temporal.tprl_content_generation.content_generator_in_workflow import ContentGeneratorInWorkflow
from pipelex.tools.storage.in_memory_storage_provider import InMemoryStorageProvider


def _make_generator() -> ContentGeneratorInWorkflow:
    factory = GeneratedContentFactory(storage_provider=InMemoryStorageProvider())
    return ContentGeneratorInWorkflow(generated_content_factory=factory)


def _patch_workflow_info(mocker: MockerFixture, workflow_id: str, run_id: str) -> None:
    """Reconfigure the ``workflow.info()`` mock to return the given identifiers
    for the next ``_record_activity_id`` call.
    """
    fake_info = mocker.MagicMock()
    fake_info.workflow_id = workflow_id
    fake_info.run_id = run_id
    mocker.patch("temporalio.workflow.info", return_value=fake_info)


class TestSeenActivityIdsLru:
    """``_seen_activity_ids`` evicts oldest runs once it exceeds the cap."""

    def test_lru_evicts_oldest_run_when_cap_exceeded(self, mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch) -> None:
        """Inserting more than ``_MAX_SEEN_RUNS`` distinct ``(workflow_id, run_id)``
        keys evicts the oldest entries by insertion order; the cap is honored.
        """
        mocker.patch("temporalio.workflow.unsafe.is_replaying", return_value=False)
        cap = 4
        monkeypatch.setattr(ContentGeneratorInWorkflow, "_MAX_SEEN_RUNS", cap)
        generator = _make_generator()

        for index in range(cap + 5):
            _patch_workflow_info(mocker, workflow_id="wf", run_id=f"run-{index}")
            generator._record_activity_id(activity_id="some-id", method_name="test")  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        # Cache must be capped at exactly ``cap`` entries.
        assert len(generator._seen_activity_ids) == cap  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
        # Oldest runs were evicted; only the last ``cap`` remain.
        remaining_run_ids = {key[1] for key in generator._seen_activity_ids}  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
        expected_run_ids = {f"run-{index}" for index in range(5, 5 + cap)}
        assert remaining_run_ids == expected_run_ids

    def test_lru_refreshes_existing_run_on_touch(self, mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch) -> None:
        """When a known run records another activity_id, it moves to the
        most-recent position so it survives subsequent evictions even when
        older-than-it new runs come in afterwards.
        """
        mocker.patch("temporalio.workflow.unsafe.is_replaying", return_value=False)
        cap = 3
        monkeypatch.setattr(ContentGeneratorInWorkflow, "_MAX_SEEN_RUNS", cap)
        generator = _make_generator()

        # Insert run-0, run-1, run-2 in order (cap is full).
        for index in range(cap):
            _patch_workflow_info(mocker, workflow_id="wf", run_id=f"run-{index}")
            generator._record_activity_id(activity_id="first", method_name="test")  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
        # Touch run-0 by recording another activity_id under it — it should
        # move to the most-recent slot.
        _patch_workflow_info(mocker, workflow_id="wf", run_id="run-0")
        generator._record_activity_id(activity_id="second", method_name="test")  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
        # Insert run-3 — should evict run-1 (oldest after the touch), not run-0.
        _patch_workflow_info(mocker, workflow_id="wf", run_id="run-3")
        generator._record_activity_id(activity_id="first", method_name="test")  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        remaining_run_ids = {key[1] for key in generator._seen_activity_ids}  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
        assert remaining_run_ids == {"run-0", "run-2", "run-3"}, (
            f"Expected run-1 evicted (touched run-0 moved to most-recent), got {remaining_run_ids!r}"
        )

    def test_replay_skip_leaves_lru_untouched(self, mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch) -> None:
        """Replay must not mutate the cache. Otherwise replay determinism
        would depend on per-process cache state, which can be evicted between
        runs.
        """
        mocker.patch("temporalio.workflow.unsafe.is_replaying", return_value=True)
        monkeypatch.setattr(ContentGeneratorInWorkflow, "_MAX_SEEN_RUNS", 4)
        generator = _make_generator()

        for index in range(10):
            _patch_workflow_info(mocker, workflow_id="wf", run_id=f"run-{index}")
            generator._record_activity_id(activity_id="some-id", method_name="test")  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        # No insertions happened — the cache is still empty.
        assert len(generator._seen_activity_ids) == 0  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
