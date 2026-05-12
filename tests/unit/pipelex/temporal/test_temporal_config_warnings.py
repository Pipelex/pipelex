"""Unit tests for ``Temporal.warn_on_unknown_routing_queues``.

When ``activity_queues.*.default`` or ``activity_queues.*.by_handle.*`` names
a queue with no ``queue_options`` entry (and which isn't the worker's
``default_task_queue``), the config-load validator must emit a WARN — typos
in routing tables should surface in CI rather than at runtime as silent misroutes.
"""

import logging
from datetime import timedelta

import pytest

from pipelex.temporal.config_temporal import (
    BUILTIN_SEARCH_ATTRIBUTES,
    ActivityRouteConfig,
    PayloadCodecConfig,
    QueueOptions,
    RetryPolicyConfig,
    SearchAttributesConfig,
    SecretMethod,
    Temporal,
    TemporalConfig,
    TemporalLogConfig,
    TemporalServerConfig,
    WorkerConfig,
    WorkerRuntimeProfile,
    WorkerRuntimeProfilesConfig,
    WorkerScope,
    WorkerScopesConfig,
    WorkerTuningMode,
)
from pipelex.tools.storage.storage_config import StorageProviderConfig


def _make_storage_provider_config() -> StorageProviderConfig:
    return StorageProviderConfig.model_validate({"method": "in_memory", "in_memory": {"uri_format": "{hash}"}})


def _make_temporal_config(activity_queues: dict[str, ActivityRouteConfig], queue_options: dict[str, QueueOptions]) -> Temporal:
    """Build a minimal valid Temporal config for warn-validation tests.

    All non-test fields are filled with sensible defaults; only
    ``activity_queues`` and ``queue_options`` matter for the warn-validation
    logic under test.
    """
    return Temporal(
        is_enabled=True,
        temporal_config=TemporalConfig(
            temporal_server_configs={
                "local": TemporalServerConfig(
                    description="local",
                    target_host="localhost:7233",
                    namespace="default",
                    api_key_method=SecretMethod.NONE,
                    api_key_id="",
                ),
            },
            selected_server="local",
            temporal_log_config=TemporalLogConfig(
                is_workflow_info_on_message=False,
                is_workflow_info_on_extra=True,
                is_full_workflow_info_on_extra=False,
                is_activity_info_on_message=False,
                is_activity_info_on_extra=True,
                is_full_activity_info_on_extra=False,
                is_formatter_enabled=True,
                is_prefix_enabled=True,
                managed_loggers=[],
                is_dispatch_resolution_traced=False,
            ),
        ),
        worker_config=WorkerConfig(
            default_task_queue="default_q",
            activity_queues=activity_queues,
            workflow_execution_timeout=timedelta(hours=1),
            default_activity_start_to_close_timeout=timedelta(minutes=10),
            retry_policy_config=RetryPolicyConfig(
                initial_interval=timedelta(seconds=3),
                backoff_coefficient=2.0,
                maximum_interval="unlimited",
                maximum_attempts=3,
                non_retryable_error_types=[],
            ),
        ),
        queue_options=queue_options,
        worker_runtime_profiles=WorkerRuntimeProfilesConfig(
            default_profile="default",
            profiles={
                "default": WorkerRuntimeProfile(
                    tuning_mode=WorkerTuningMode.EXPLICIT,
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
                ),
            },
        ),
        worker_scopes=WorkerScopesConfig(
            default_scope="full",
            scopes={
                "full": WorkerScope(
                    required_tasks_packs=[],
                    required_workflows=[],
                    required_activities=[],
                    excluded_workflows=[],
                    excluded_activities=[],
                    disable_all_workflows=False,
                    disable_all_activities=False,
                ),
            },
        ),
        payload_codec_config=PayloadCodecConfig(
            is_enabled=False,
            size_threshold=1_048_576,
            storage_prefix="prefix/",
            storage_provider_config=_make_storage_provider_config(),
        ),
        search_attributes=SearchAttributesConfig(
            enabled=True,
            attributes=list(BUILTIN_SEARCH_ATTRIBUTES),
        ),
    )


class TestTemporalConfigWarnings:
    """Lenient warn fires on routing entries that reference unknown queues."""

    def test_unknown_queue_in_activity_default_warns(self, caplog: pytest.LogCaptureFixture) -> None:
        """A ``by_handle`` entry naming a queue with no ``queue_options`` and
        not equal to ``default_task_queue`` triggers a WARN with the activity
        + handle path so the user can locate the typo.
        """
        with caplog.at_level(logging.WARNING):
            _make_temporal_config(
                activity_queues={
                    "act_llm_gen_text": ActivityRouteConfig(
                        default="default_q",
                        by_handle={"claude-opus-4-7": "anthrpic_q"},  # typo
                    ),
                },
                queue_options={},
            )
        warnings = [record for record in caplog.records if record.levelno == logging.WARNING]
        assert any("anthrpic_q" in record.message for record in warnings), (
            f"expected warning about 'anthrpic_q', got: {[r.message for r in warnings]!r}"
        )

    def test_no_warning_when_queue_in_queue_options(self, caplog: pytest.LogCaptureFixture) -> None:
        """A queue present in ``queue_options`` is known — no warning fires."""
        with caplog.at_level(logging.WARNING):
            _make_temporal_config(
                activity_queues={
                    "act_llm_gen_text": ActivityRouteConfig(
                        default="anthropic_q",
                        by_handle={},
                    ),
                },
                queue_options={"anthropic_q": QueueOptions(start_to_close_timeout=timedelta(minutes=5))},
            )
        relevant_warnings = [record for record in caplog.records if "anthropic_q" in record.message and record.levelno == logging.WARNING]
        assert not relevant_warnings, f"expected no warning for known queue, got: {[r.message for r in relevant_warnings]!r}"

    def test_default_task_queue_is_known_without_queue_options(self, caplog: pytest.LogCaptureFixture) -> None:
        """``default_task_queue`` is implicitly known — no warning even when no
        ``queue_options`` entry exists for it.
        """
        with caplog.at_level(logging.WARNING):
            _make_temporal_config(
                activity_queues={
                    "act_llm_gen_text": ActivityRouteConfig(default="default_q", by_handle={}),
                },
                queue_options={},
            )
        relevant_warnings = [record for record in caplog.records if "default_q" in record.message and record.levelno == logging.WARNING]
        assert not relevant_warnings, f"unexpected warning for default_task_queue: {[r.message for r in relevant_warnings]!r}"

    def test_unreachable_queue_options_entry_warns(self, caplog: pytest.LogCaptureFixture) -> None:
        """``queue_options`` entry naming a queue that no ``activity_queues``
        route references AND that isn't ``default_task_queue`` triggers a WARN —
        the overlay will never apply and is almost always a typo or stale entry.
        """
        with caplog.at_level(logging.WARNING):
            _make_temporal_config(
                activity_queues={},
                queue_options={"orphan_q": QueueOptions(start_to_close_timeout=timedelta(minutes=5))},
            )
        warnings = [record for record in caplog.records if record.levelno == logging.WARNING]
        assert any("orphan_q" in record.message and "overlay will never apply" in record.message for record in warnings), (
            f"expected warning about 'orphan_q' overlay never applying, got: {[r.message for r in warnings]!r}"
        )

    def test_default_task_queue_in_queue_options_does_not_warn(self, caplog: pytest.LogCaptureFixture) -> None:
        """``queue_options[default_task_queue]`` is the supported single-queue
        tuning path — it must not trigger the unreachable-overlay warning even
        with empty ``activity_queues``.
        """
        with caplog.at_level(logging.WARNING):
            _make_temporal_config(
                activity_queues={},
                queue_options={"default_q": QueueOptions(start_to_close_timeout=timedelta(minutes=5))},
            )
        unreachable_warnings = [
            record
            for record in caplog.records
            if record.levelno == logging.WARNING and "default_q" in record.message and "overlay will never apply" in record.message
        ]
        assert not unreachable_warnings, (
            f"unexpected unreachable-overlay warning for default_task_queue: {[r.message for r in unreachable_warnings]!r}"
        )
