"""Unit tests for ``TemporalTaskManager._resolve_runtime_profile_by_name`` and
the ``WorkerTuningMode`` validator on ``WorkerRuntimeProfile``.

Mirrors the structure of ``test_worker_scope_resolution.py`` — exercises the
named-profile lookup including the unknown-profile error and the explicit
rejection of ``tuning_mode='resource_based'`` until that path ships.
"""

from datetime import timedelta

import pytest
from pydantic import ValidationError

from pipelex.system.configuration.config_temporal import WorkerRuntimeProfile, WorkerTuningMode
from pipelex.temporal.exceptions import WorkerProfileConfigError
from pipelex.temporal.temporal_task_manager import TemporalTaskManager


class TestWorkerRuntimeProfile:
    """Resolution of named runtime profiles + rejection of unimplemented tuning_mode."""

    def test_default_profile_resolves_when_none(self) -> None:
        """When ``profile_name=None``, resolution returns the configured ``default_profile``."""
        profile = TemporalTaskManager._resolve_runtime_profile_by_name(profile_name=None)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
        # Out-of-the-box default ships the values lifted from the pre-v2 Worker(...)
        # construction. Test against the most distinctive field rather than the
        # exact instance (which would couple to TOML loading).
        assert profile.max_concurrent_activities == 1000

    def test_named_profile_resolves(self) -> None:
        """Passing an explicit name resolves to that profile from config."""
        # `default` is always present in shipping pipelex.toml.
        profile = TemporalTaskManager._resolve_runtime_profile_by_name(profile_name="default")  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
        assert profile.max_concurrent_activities == 1000

    def test_unknown_profile_raises_with_known_names(self) -> None:
        """An unknown profile name raises ``WorkerProfileConfigError`` with the
        full list of known profiles in the message.
        """
        with pytest.raises(WorkerProfileConfigError) as exc_info:
            TemporalTaskManager._resolve_runtime_profile_by_name(profile_name="nonexistent-profile")  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
        message = str(exc_info.value)
        assert "nonexistent-profile" in message
        # Default profile is always known and must appear in the listing.
        assert "default" in message

    def test_resource_based_tuning_mode_rejected(self) -> None:
        """``WorkerTuningMode.RESOURCE_BASED`` is reserved for a future iteration;
        constructing a profile with that mode must raise immediately with a
        clear "not implemented" message.

        Pydantic v2 wraps validator-raised exceptions in ``ValidationError``;
        the assertion checks the wrapped message rather than the exception class.
        """
        with pytest.raises(ValidationError) as exc_info:
            WorkerRuntimeProfile(
                tuning_mode=WorkerTuningMode.RESOURCE_BASED,
                max_cached_workflows=10000,
                max_concurrent_workflow_tasks=1000,
                max_concurrent_activities=1000,
                max_concurrent_local_activities=1000,
                max_concurrent_workflow_task_polls=100,
                max_concurrent_activity_task_polls=100,
                max_activities_per_second=1000,
                sticky_queue_schedule_to_start_timeout=timedelta(minutes=30),
                max_heartbeat_throttle_interval=timedelta(minutes=60),
                default_heartbeat_throttle_interval=timedelta(minutes=60),
                graceful_shutdown_timeout=timedelta(minutes=30),
            )
        message = str(exc_info.value)
        assert "resource_based" in message
        assert "explicit" in message
