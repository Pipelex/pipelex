"""Unit tests for ``Temporal.validate_no_orphan_queue_references``.

When ``activity_queues.*.default`` or ``activity_queues.*.by_handle.*`` names
a queue with no ``queue_options`` entry (and which isn't the worker's
``default_task_queue``), the config-load validator must raise
``TemporalConfigError`` so typos surface at boot rather than at runtime as
silent misroutes.

Pydantic wraps ``TemporalConfigError`` (a ``ValueError`` subclass) in
``pydantic.ValidationError`` when raised from a ``model_validator``, so tests
match on ``ValidationError`` and inspect the message for the offending queue.
"""

from datetime import timedelta

import pytest
from pydantic import ValidationError

from pipelex.system.configuration.config_temporal import (
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
    """Build a minimal valid Temporal config for orphan-queue validation tests.

    All non-test fields are filled with sensible defaults; only
    ``activity_queues`` and ``queue_options`` matter for the validation logic
    under test.
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


class TestTemporalConfigOrphanQueues:
    """Config-load fails on routing entries that reference unknown queues."""

    def test_unknown_queue_in_activity_by_handle_raises(self) -> None:
        """A ``by_handle`` entry naming a queue with no ``queue_options`` and
        not equal to ``default_task_queue`` raises with the activity + handle
        path and a fix suggestion.
        """
        with pytest.raises(ValidationError, match="anthrpic_q") as exc_info:
            _make_temporal_config(
                activity_queues={
                    "act_llm_gen_text": ActivityRouteConfig(
                        default="default_q",
                        by_handle={"claude-opus-4-7": "anthrpic_q"},  # typo
                    ),
                },
                queue_options={},
            )
        message = str(exc_info.value)
        assert "act_llm_gen_text" in message
        assert "claude-opus-4-7" in message
        assert "[temporal.queue_options.anthrpic_q]" in message

    def test_unknown_queue_in_activity_default_raises(self) -> None:
        """An ``activity_queues.*.default`` entry naming a queue with no
        ``queue_options`` and not equal to ``default_task_queue`` raises with
        a fix suggestion that names the orphan queue.
        """
        with pytest.raises(ValidationError, match="missing_q") as exc_info:
            _make_temporal_config(
                activity_queues={
                    "act_llm_gen_text": ActivityRouteConfig(
                        default="missing_q",
                        by_handle={},
                    ),
                },
                queue_options={},
            )
        message = str(exc_info.value)
        assert "[temporal.queue_options.missing_q]" in message
        assert "activity_queues.act_llm_gen_text.default" in message

    def test_no_error_when_queue_in_queue_options(self) -> None:
        """A queue present in ``queue_options`` is known — config loads."""
        _make_temporal_config(
            activity_queues={
                "act_llm_gen_text": ActivityRouteConfig(
                    default="anthropic_q",
                    by_handle={},
                ),
            },
            queue_options={"anthropic_q": QueueOptions(start_to_close_timeout=timedelta(minutes=5))},
        )

    def test_empty_queue_options_stanza_is_sufficient(self) -> None:
        """An empty ``[temporal.queue_options.<q>]`` stanza is the explicit
        "use worker_config defaults" declaration and satisfies the validator.
        """
        _make_temporal_config(
            activity_queues={
                "act_llm_gen_text": ActivityRouteConfig(default="my_q", by_handle={}),
            },
            queue_options={"my_q": QueueOptions()},
        )

    def test_default_task_queue_is_known_without_queue_options(self) -> None:
        """``default_task_queue`` is implicitly known — config loads even
        when no ``queue_options`` entry exists for it.
        """
        _make_temporal_config(
            activity_queues={
                "act_llm_gen_text": ActivityRouteConfig(default="default_q", by_handle={}),
            },
            queue_options={},
        )

    def test_unreachable_queue_options_entry_raises(self) -> None:
        """A ``queue_options`` entry naming a queue that no ``activity_queues``
        route references AND that isn't ``default_task_queue`` raises — the
        overlay would never apply.
        """
        with pytest.raises(ValidationError, match="orphan_q") as exc_info:
            _make_temporal_config(
                activity_queues={},
                queue_options={"orphan_q": QueueOptions(start_to_close_timeout=timedelta(minutes=5))},
            )
        message = str(exc_info.value)
        assert "overlay will never apply" in message
        assert "[temporal.queue_options.orphan_q]" in message

    def test_default_task_queue_in_queue_options_does_not_raise(self) -> None:
        """``queue_options[default_task_queue]`` is the supported single-queue
        tuning path — it must not trigger the unreachable-overlay error even
        with empty ``activity_queues``.
        """
        _make_temporal_config(
            activity_queues={},
            queue_options={"default_q": QueueOptions(start_to_close_timeout=timedelta(minutes=5))},
        )
