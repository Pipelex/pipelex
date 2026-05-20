"""Unit tests for the Pydantic field validators on ``QueueOptions``,
``HandleOptions``, ``WorkerRuntimeProfile``, and ``RetryPolicyConfigBase``.

These guards reject negative/zero values that would pass Pydantic's basic
type coercion but cause runtime errors at the Temporal SDK boundary
(``Worker(...)``, ``workflow.execute_activity(...)``). Catching them at
config load gives a clear error pointing at the offending field instead of
a cryptic SDK error mid-workflow.
"""

from datetime import timedelta

import pytest
from pydantic import ValidationError

from pipelex.temporal.config_temporal import (
    HandleOptions,
    QueueOptions,
    RetryPolicyConfig,
    RetryPolicyConfigOverlay,
    WorkerRuntimeProfile,
    WorkerTuningMode,
)


def _valid_profile_kwargs() -> dict[str, object]:
    """Build a kwargs dict for ``WorkerRuntimeProfile`` with all valid values.
    Tests override one field at a time to verify each validator independently.
    """
    return {
        "tuning_mode": WorkerTuningMode.EXPLICIT,
        "max_cached_workflows": 10000,
        "max_concurrent_workflow_tasks": 1000,
        "max_concurrent_activities": 1000,
        "max_concurrent_local_activities": 1000,
        "max_concurrent_workflow_task_polls": 100,
        "max_concurrent_activity_task_polls": 100,
        "max_activities_per_second": 1000,
        "sticky_queue_schedule_to_start_timeout": timedelta(minutes=30),
        "max_heartbeat_throttle_interval": timedelta(minutes=60),
        "default_heartbeat_throttle_interval": timedelta(minutes=60),
        "graceful_shutdown_timeout": timedelta(minutes=30),
    }


class TestConfigFieldValidators:
    """Reject non-positive timedeltas + zero/negative ints/floats where invalid."""

    @pytest.mark.parametrize(
        "field_name",
        [
            "start_to_close_timeout",
            "schedule_to_close_timeout",
            "schedule_to_start_timeout",
            "heartbeat_timeout",
        ],
    )
    def test_queue_options_rejects_non_positive_timedelta(self, field_name: str) -> None:
        """Each ``QueueOptions`` timedelta field rejects zero and negative."""
        with pytest.raises(ValidationError) as exc_info:
            QueueOptions(**{field_name: timedelta(seconds=-5)})  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]
        errors = exc_info.value.errors()
        assert any(err["loc"] == (field_name,) and err["type"] == "greater_than" for err in errors)
        with pytest.raises(ValidationError):
            QueueOptions(**{field_name: timedelta(0)})  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]

    def test_queue_options_rejects_non_positive_rate_cap(self) -> None:
        """``max_task_queue_activities_per_second`` must be > 0."""
        with pytest.raises(ValidationError):
            QueueOptions(max_task_queue_activities_per_second=0)
        with pytest.raises(ValidationError):
            QueueOptions(max_task_queue_activities_per_second=-1.5)

    def test_queue_options_accepts_none_and_positive_values(self) -> None:
        """Sanity: all-None and explicitly positive values still construct."""
        QueueOptions()  # all defaults / None — must not raise
        QueueOptions(
            start_to_close_timeout=timedelta(minutes=5),
            heartbeat_timeout=timedelta(seconds=30),
            max_task_queue_activities_per_second=100,
        )

    def test_handle_options_rejects_non_positive_start_to_close(self) -> None:
        """``HandleOptions.start_to_close_timeout`` must be positive."""
        with pytest.raises(ValidationError):
            HandleOptions(start_to_close_timeout=timedelta(seconds=-1))
        with pytest.raises(ValidationError):
            HandleOptions(start_to_close_timeout=timedelta(0))
        # Positive and None both fine.
        HandleOptions()
        HandleOptions(start_to_close_timeout=timedelta(minutes=10))

    @pytest.mark.parametrize(
        ("field_name", "bad_value"),
        [
            ("max_concurrent_workflow_tasks", 0),  # gt=0: 0 unsafe (worker can't progress)
            ("max_concurrent_workflow_tasks", -1),
            ("max_concurrent_workflow_task_polls", 0),
            ("max_concurrent_workflow_task_polls", -1),
            ("max_cached_workflows", -1),  # ge=0
            ("max_concurrent_activities", -1),
            ("max_concurrent_local_activities", -1),
            ("max_concurrent_activity_task_polls", -1),
        ],
    )
    def test_worker_runtime_profile_rejects_invalid_int(self, field_name: str, bad_value: int) -> None:
        kwargs = _valid_profile_kwargs()
        kwargs[field_name] = bad_value
        with pytest.raises(ValidationError):
            WorkerRuntimeProfile(**kwargs)  # type: ignore[arg-type]

    def test_worker_runtime_profile_accepts_zero_concurrent_activities(self) -> None:
        """Workflow-only worker pattern: ``max_concurrent_activities = 0``
        is valid (router profile example uses this).
        """
        kwargs = _valid_profile_kwargs()
        kwargs["max_concurrent_activities"] = 0
        kwargs["max_concurrent_activity_task_polls"] = 0
        WorkerRuntimeProfile(**kwargs)  # type: ignore[arg-type]  # must not raise

    @pytest.mark.parametrize("bad_value", [0, -10.0])
    def test_worker_runtime_profile_rejects_non_positive_rate(self, bad_value: float) -> None:
        """``max_activities_per_second`` must be > 0."""
        kwargs = _valid_profile_kwargs()
        kwargs["max_activities_per_second"] = bad_value
        with pytest.raises(ValidationError):
            WorkerRuntimeProfile(**kwargs)  # type: ignore[arg-type]

    @pytest.mark.parametrize(
        "field_name",
        [
            "sticky_queue_schedule_to_start_timeout",
            "max_heartbeat_throttle_interval",
            "default_heartbeat_throttle_interval",
            "graceful_shutdown_timeout",
        ],
    )
    @pytest.mark.parametrize("bad_value", [timedelta(seconds=-1), timedelta(0)])
    def test_worker_runtime_profile_rejects_non_positive_timedelta(self, field_name: str, bad_value: timedelta) -> None:
        """Both negative and zero must be rejected — ``gt=timedelta(0)`` is the right
        bound (a heartbeat throttle of 0 would mean "throttle immediately" and break
        the worker).
        """
        kwargs = _valid_profile_kwargs()
        kwargs[field_name] = bad_value
        with pytest.raises(ValidationError):
            WorkerRuntimeProfile(**kwargs)  # type: ignore[arg-type]

    @pytest.mark.parametrize("bad_value", [timedelta(seconds=-1), timedelta(0)])
    def test_retry_policy_config_rejects_non_positive_initial_interval(self, bad_value: timedelta) -> None:
        """``initial_interval`` is the seed delay between the first attempt and the
        first retry. ``gt=timedelta(0)`` rejects both negative and zero.
        """
        with pytest.raises(ValidationError):
            RetryPolicyConfig(
                initial_interval=bad_value,
                backoff_coefficient=2.0,
                maximum_interval="unlimited",
                maximum_attempts=3,
                non_retryable_error_types=[],
            )

    @pytest.mark.parametrize("bad_value", [timedelta(seconds=-1), timedelta(0)])
    def test_retry_policy_config_rejects_non_positive_maximum_interval(self, bad_value: timedelta) -> None:
        """Either a positive timedelta or the literal 'unlimited' — both negative
        and zero are rejected by the ``Annotated[timedelta, Field(gt=...)]`` branch
        of the Union.
        """
        with pytest.raises(ValidationError):
            RetryPolicyConfig(
                initial_interval=timedelta(seconds=3),
                backoff_coefficient=2.0,
                maximum_interval=bad_value,
                maximum_attempts=3,
                non_retryable_error_types=[],
            )

    @pytest.mark.parametrize("bad_value", [0, -1, -100])
    def test_retry_policy_config_rejects_non_positive_maximum_attempts(self, bad_value: int) -> None:
        """Either a positive int or the literal 'unlimited' — zero and negatives
        are rejected by the ``Annotated[int, Field(gt=0)]`` branch of the Union.
        """
        with pytest.raises(ValidationError):
            RetryPolicyConfig(
                initial_interval=timedelta(seconds=3),
                backoff_coefficient=2.0,
                maximum_interval="unlimited",
                maximum_attempts=bad_value,
                non_retryable_error_types=[],
            )

    def test_retry_policy_overlay_inherits_validators(self) -> None:
        """The overlay subclass inherits the validators from the base — both
        layers must reject the same invalid values, so a per-queue override
        can't silently smuggle in a bad scalar.
        """
        with pytest.raises(ValidationError):
            RetryPolicyConfigOverlay(
                initial_interval=timedelta(0),
                backoff_coefficient=2.0,
                maximum_interval="unlimited",
                maximum_attempts=3,
                non_retryable_error_types_extra=[],
            )

    def test_retry_policy_accepts_unlimited_literals(self) -> None:
        """The Literal['unlimited'] escape hatches must not be rejected by the
        positive-timedelta / positive-int validators.
        """
        RetryPolicyConfig(
            initial_interval=timedelta(seconds=3),
            backoff_coefficient=2.0,
            maximum_interval="unlimited",
            maximum_attempts="unlimited",
            non_retryable_error_types=[],
        )

    def test_retry_policy_accepts_concrete_positive_union_branches(self) -> None:
        """Happy path for the ``Annotated[..., Field(gt=...)]`` branches of the two
        Unions: a positive timedelta for ``maximum_interval`` and a positive int
        for ``maximum_attempts``. Complements ``test_retry_policy_accepts_unlimited_literals``
        which exercises the ``Literal['unlimited']`` branch.
        """
        config = RetryPolicyConfig(
            initial_interval=timedelta(seconds=3),
            backoff_coefficient=2.0,
            maximum_interval=timedelta(minutes=5),
            maximum_attempts=10,
            non_retryable_error_types=[],
        )
        assert config.maximum_interval == timedelta(minutes=5)
        assert config.maximum_attempts == 10

    def test_retry_policy_rejects_backoff_coefficient_below_one(self) -> None:
        """``backoff_coefficient < 1`` would shrink retry intervals over time
        — almost certainly a typo. Pydantic ge=1.0 catches it.
        """
        with pytest.raises(ValidationError):
            RetryPolicyConfig(
                initial_interval=timedelta(seconds=3),
                backoff_coefficient=0.5,
                maximum_interval="unlimited",
                maximum_attempts=3,
                non_retryable_error_types=[],
            )
