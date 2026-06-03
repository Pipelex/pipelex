"""Unit tests for ``WorkerConfig.all_non_retryable_error_types``.

The helper unions every ``non_retryable_error_types`` declared anywhere in the
temporal config: baseline main list + every queue overlay's ``_extra`` +
every handle overlay's ``_extra``. ``TemporalError.from_app_error`` uses it
for ApplicationError severity classification — the error-handling site sees
only the error type string and can't know which overlay contributed the entry,
so the union must be precomputed.

Retry *behavior* is correct via the dispatch-time ``retry_policy`` (that path
is covered by ``test_resolve_dispatch.py::test_non_retryable_additive``).
These tests cover only the log-severity union.
"""

from datetime import timedelta

from pipelex.temporal.config_temporal import (
    ActivityRouteConfig,
    HandleOptions,
    QueueOptions,
    RetryPolicyConfig,
    RetryPolicyConfigOverlay,
    WorkerConfig,
)


def _make_baseline_retry(non_retryable: list[str] | None = None) -> RetryPolicyConfig:
    return RetryPolicyConfig(
        initial_interval=timedelta(seconds=3),
        backoff_coefficient=2.0,
        maximum_interval="unlimited",
        maximum_attempts=3,
        non_retryable_error_types=non_retryable or [],
    )


def _make_overlay_retry(non_retryable_extra: list[str] | None = None) -> RetryPolicyConfigOverlay:
    return RetryPolicyConfigOverlay(
        initial_interval=timedelta(seconds=3),
        backoff_coefficient=2.0,
        maximum_interval="unlimited",
        maximum_attempts=3,
        non_retryable_error_types_extra=non_retryable_extra or [],
    )


def _make_worker_config(
    activity_queues: dict[str, ActivityRouteConfig] | None = None,
    baseline_non_retryable: list[str] | None = None,
) -> WorkerConfig:
    return WorkerConfig(
        default_task_queue="default_q",
        activity_queues=activity_queues or {},
        workflow_execution_timeout=timedelta(hours=1),
        default_activity_start_to_close_timeout=timedelta(minutes=10),
        retry_policy_config=_make_baseline_retry(baseline_non_retryable),
    )


class TestAllNonRetryableErrorTypes:
    """Union across baseline + every queue overlay + every handle overlay."""

    def test_baseline_only(self) -> None:
        """No overlays anywhere → result equals the baseline main list."""
        worker_config = _make_worker_config(baseline_non_retryable=["ValidationError", "ModelNotFoundError"])
        result = worker_config.all_non_retryable_error_types(queue_options_by_queue={})
        assert result == {"ValidationError", "ModelNotFoundError"}

    def test_queue_overlay_extras_are_included(self) -> None:
        """Every queue overlay's ``_extra`` contributes regardless of routing."""
        worker_config = _make_worker_config(baseline_non_retryable=["ValidationError"])
        queue_options = {
            "anthropic_q": QueueOptions(retry_policy_config=_make_overlay_retry(["AnthropicBadRequest"])),
            "openai_q": QueueOptions(retry_policy_config=_make_overlay_retry(["OpenAIBadRequest"])),
            # Queue without retry overlay still mustn't break the union.
            "vanilla_q": QueueOptions(start_to_close_timeout=timedelta(minutes=3)),
        }
        result = worker_config.all_non_retryable_error_types(queue_options_by_queue=queue_options)
        assert result == {"ValidationError", "AnthropicBadRequest", "OpenAIBadRequest"}

    def test_handle_overlay_extras_are_included(self) -> None:
        """Every handle overlay's ``_extra`` contributes regardless of routing."""
        worker_config = _make_worker_config(
            baseline_non_retryable=["ValidationError"],
            activity_queues={
                "act_llm_gen_text": ActivityRouteConfig(
                    default="anthropic_q",
                    handle_options={
                        "claude-opus-4-7-1m": HandleOptions(
                            retry_policy_config=_make_overlay_retry(["HandleSpecificError"]),
                        ),
                        # Handle without retry overlay still mustn't break the union.
                        "claude-opus-4-7": HandleOptions(start_to_close_timeout=timedelta(minutes=15)),
                    },
                ),
            },
        )
        result = worker_config.all_non_retryable_error_types(queue_options_by_queue={})
        assert result == {"ValidationError", "HandleSpecificError"}

    def test_dedupe_across_baseline_queue_handle(self) -> None:
        """Entries repeating across layers collapse to a single set entry."""
        worker_config = _make_worker_config(
            baseline_non_retryable=["ValidationError"],
            activity_queues={
                "act_llm_gen_text": ActivityRouteConfig(
                    default="anthropic_q",
                    handle_options={
                        "claude-opus-4-7-1m": HandleOptions(
                            retry_policy_config=_make_overlay_retry(["ValidationError", "HandleSpecificError"]),
                        ),
                    },
                ),
            },
        )
        queue_options = {
            "anthropic_q": QueueOptions(
                retry_policy_config=_make_overlay_retry(["ValidationError", "AnthropicBadRequest"]),
            ),
        }
        result = worker_config.all_non_retryable_error_types(queue_options_by_queue=queue_options)
        # ValidationError appears in baseline + queue + handle but only once in the union.
        assert result == {"ValidationError", "AnthropicBadRequest", "HandleSpecificError"}

    def test_empty_everything(self) -> None:
        """No baseline, no overlays → empty set, not None."""
        worker_config = _make_worker_config(baseline_non_retryable=[])
        result = worker_config.all_non_retryable_error_types(queue_options_by_queue={})
        assert result == set()
