"""Unit test: ``TemporalTaskManager.make_worker`` plumbs every
``WorkerRuntimeProfile`` field into the underlying ``Worker(...)`` constructor,
and reads ``max_task_queue_activities_per_second`` from
``queue_options[task_queue]`` when present.

Mocks the ``Worker`` class so the test runs without a Temporal server and
focuses on the kwargs contract.
"""

from datetime import timedelta

from pytest_mock import MockerFixture

from pipelex.config import get_config
from pipelex.temporal.config_temporal import QueueOptions, WorkerRuntimeProfile, WorkerTuningMode
from pipelex.temporal.temporal_task_manager import TemporalTaskManager


def _make_profile() -> WorkerRuntimeProfile:
    """Build a distinct-valued profile so every field can be uniquely asserted."""
    return WorkerRuntimeProfile(
        tuning_mode=WorkerTuningMode.EXPLICIT,
        max_cached_workflows=42,
        max_concurrent_workflow_tasks=43,
        max_concurrent_activities=44,
        max_concurrent_local_activities=45,
        max_concurrent_workflow_task_polls=46,
        max_concurrent_activity_task_polls=47,
        max_activities_per_second=48,
        sticky_queue_schedule_to_start_timeout=timedelta(minutes=10),
        max_heartbeat_throttle_interval=timedelta(minutes=20),
        default_heartbeat_throttle_interval=timedelta(minutes=30),
        graceful_shutdown_timeout=timedelta(minutes=40),
    )


class TestMakeWorkerUsesProfile:
    """Profile fields and queue rate cap flow into ``Worker(...)`` kwargs."""

    def test_every_profile_field_flows_to_worker_kwarg(self, mocker: MockerFixture) -> None:
        """Each ``WorkerRuntimeProfile`` field maps to the matching ``Worker`` kwarg."""
        worker_mock = mocker.patch("pipelex.temporal.temporal_task_manager.Worker")
        profile = _make_profile()

        TemporalTaskManager().make_worker(
            temporal_client=mocker.MagicMock(),
            task_queue="test_q",
            is_not_sandboxed=True,
            runtime_profile=profile,
        )

        worker_mock.assert_called_once()
        kwargs = worker_mock.call_args.kwargs
        assert kwargs["task_queue"] == "test_q"
        assert kwargs["max_cached_workflows"] == 42
        assert kwargs["max_concurrent_workflow_tasks"] == 43
        assert kwargs["max_concurrent_activities"] == 44
        assert kwargs["max_concurrent_local_activities"] == 45
        assert kwargs["max_concurrent_workflow_task_polls"] == 46
        assert kwargs["max_concurrent_activity_task_polls"] == 47
        assert kwargs["max_activities_per_second"] == 48
        assert kwargs["sticky_queue_schedule_to_start_timeout"] == timedelta(minutes=10)
        assert kwargs["max_heartbeat_throttle_interval"] == timedelta(minutes=20)
        assert kwargs["default_heartbeat_throttle_interval"] == timedelta(minutes=30)
        assert kwargs["graceful_shutdown_timeout"] == timedelta(minutes=40)

    def test_max_task_queue_rate_cap_from_queue_options(self, mocker: MockerFixture) -> None:
        """``max_task_queue_activities_per_second`` comes from
        ``queue_options[task_queue]`` when present, ``None`` otherwise.

        Mutates ``get_config().temporal.queue_options`` for the duration of the
        test; the ``finally`` restores prior state.
        """
        worker_mock = mocker.patch("pipelex.temporal.temporal_task_manager.Worker")
        profile = _make_profile()
        queue_options = get_config().temporal.queue_options
        test_q = "test_rate_capped_q"
        assert test_q not in queue_options, "test queue name should be unique"
        queue_options[test_q] = QueueOptions(max_task_queue_activities_per_second=17.5)
        try:
            TemporalTaskManager().make_worker(
                temporal_client=mocker.MagicMock(),
                task_queue=test_q,
                is_not_sandboxed=True,
                runtime_profile=profile,
            )
        finally:
            queue_options.pop(test_q, None)

        worker_mock.assert_called_once()
        assert worker_mock.call_args.kwargs["max_task_queue_activities_per_second"] == 17.5

    def test_max_task_queue_rate_cap_omitted_when_no_queue_options(self, mocker: MockerFixture) -> None:
        """No ``queue_options`` entry → ``max_task_queue_activities_per_second=None``
        flows to ``Worker(...)`` (the Temporal SDK treats this as 'no cap').
        """
        worker_mock = mocker.patch("pipelex.temporal.temporal_task_manager.Worker")
        profile = _make_profile()
        unconfigured_q = "test_unconfigured_q"
        assert unconfigured_q not in get_config().temporal.queue_options

        TemporalTaskManager().make_worker(
            temporal_client=mocker.MagicMock(),
            task_queue=unconfigured_q,
            is_not_sandboxed=True,
            runtime_profile=profile,
        )

        worker_mock.assert_called_once()
        assert worker_mock.call_args.kwargs["max_task_queue_activities_per_second"] is None

    def test_shipping_default_temporal_task_queue_has_1000_rate_cap(self, mocker: MockerFixture) -> None:
        """Regression guard: the shipping ``[temporal.queue_options.temporal_task_queue]``
        block sets ``max_task_queue_activities_per_second = 1000`` to preserve
        the pre-v2 hardcoded ``Worker(..., max_task_queue_activities_per_second=1000)``
        for deployments using the default queue name. Catches accidental
        removal of the baseline cap.
        """
        worker_mock = mocker.patch("pipelex.temporal.temporal_task_manager.Worker")
        profile = _make_profile()

        TemporalTaskManager().make_worker(
            temporal_client=mocker.MagicMock(),
            task_queue="temporal_task_queue",
            is_not_sandboxed=True,
            runtime_profile=profile,
        )

        worker_mock.assert_called_once()
        assert worker_mock.call_args.kwargs["max_task_queue_activities_per_second"] == 1000
