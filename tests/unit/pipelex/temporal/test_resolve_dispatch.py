"""Unit tests for ``WorkerConfig.resolve_dispatch`` — the submitter-side
resolution chain that returns a ``DispatchOptions`` bundle for every
``workflow.execute_activity(...)`` call.

Covers the three layering layers (baseline → queue_options → handle_options)
for scalars (last-wins) and the additive composition of
``non_retryable_error_types``.
"""

from datetime import timedelta

import pytest
from pydantic import ValidationError

from pipelex.temporal.config_temporal import (
    ActivityRouteConfig,
    HandleOptions,
    QueueOptions,
    RetryPolicyConfig,
    WorkerConfig,
)


def _make_baseline_retry(non_retryable: list[str] | None = None) -> RetryPolicyConfig:
    return RetryPolicyConfig(
        initial_interval=timedelta(seconds=3),
        backoff_coefficient=2.0,
        maximum_interval="unlimited",
        maximum_attempts=3,
        non_retryable_error_types=non_retryable or ["ValidationError"],
        non_retryable_error_types_extra=[],
    )


def _make_worker_config(
    activity_queues: dict[str, ActivityRouteConfig] | None = None,
    baseline_start_to_close: timedelta | None = None,
    baseline_heartbeat: timedelta | None = None,
    baseline_non_retryable: list[str] | None = None,
) -> WorkerConfig:
    return WorkerConfig(
        default_task_queue="default_q",
        activity_queues=activity_queues or {},
        workflow_execution_timeout=timedelta(hours=1),
        default_activity_start_to_close_timeout=baseline_start_to_close or timedelta(minutes=10),
        default_activity_heartbeat_timeout=baseline_heartbeat,
        retry_policy_config=_make_baseline_retry(baseline_non_retryable),
    )


class TestResolveDispatch:
    """Three-layer last-wins for scalars + additive composition for non_retryable."""

    def test_no_overrides_uses_baseline(self) -> None:
        """With no queue_options and no handle_options, dispatch comes from the
        worker_config baseline values verbatim.
        """
        worker_config = _make_worker_config()

        dispatch = worker_config.resolve_dispatch(activity_name="act_llm_gen_text", routing_key="claude-opus-4-7")

        assert dispatch.task_queue == "default_q"
        assert dispatch.start_to_close_timeout == timedelta(minutes=10)
        assert dispatch.heartbeat_timeout is None
        # Baseline retry has one non-retryable; resolved policy must surface it.
        kwargs = dispatch.to_execute_kwargs()
        assert "task_queue" in kwargs
        assert "start_to_close_timeout" in kwargs
        assert "retry_policy" in kwargs
        # Optional timeouts are omitted when None — Temporal SDK rejects None values.
        assert "schedule_to_close_timeout" not in kwargs
        assert "heartbeat_timeout" not in kwargs

    def test_queue_options_override_baseline(self) -> None:
        """When ``queue_options[resolved_queue]`` provides a scalar, it overrides
        the worker_config baseline.
        """
        worker_config = _make_worker_config(
            activity_queues={
                "act_llm_gen_text": ActivityRouteConfig(default="anthropic_q"),
            },
        )
        queue_options = {
            "anthropic_q": QueueOptions(
                start_to_close_timeout=timedelta(minutes=5),
                heartbeat_timeout=timedelta(seconds=30),
            ),
        }

        dispatch = worker_config.resolve_dispatch(
            activity_name="act_llm_gen_text",
            routing_key="claude-opus-4-7",
            queue_options_by_queue=queue_options,
        )

        assert dispatch.task_queue == "anthropic_q"
        assert dispatch.start_to_close_timeout == timedelta(minutes=5)
        assert dispatch.heartbeat_timeout == timedelta(seconds=30)

    def test_handle_options_override_queue(self) -> None:
        """A per-handle ``handle_options.start_to_close_timeout`` wins over the
        queue-level value (deepest layer wins for scalars).
        """
        worker_config = _make_worker_config(
            activity_queues={
                "act_llm_gen_text": ActivityRouteConfig(
                    default="anthropic_q",
                    handle_options={
                        "claude-opus-4-7-1m": HandleOptions(start_to_close_timeout=timedelta(minutes=25)),
                    },
                ),
            },
        )
        queue_options = {
            "anthropic_q": QueueOptions(start_to_close_timeout=timedelta(minutes=5)),
        }

        dispatch = worker_config.resolve_dispatch(
            activity_name="act_llm_gen_text",
            routing_key="claude-opus-4-7-1m",
            queue_options_by_queue=queue_options,
        )

        assert dispatch.start_to_close_timeout == timedelta(minutes=25)

    def test_non_retryable_additive(self) -> None:
        """``non_retryable_error_types`` composes additively across all layers
        (baseline + queue extra + handle extra). Deduplication preserves the
        result as a deterministic ordered list with no duplicates.
        """
        worker_config = _make_worker_config(
            baseline_non_retryable=["ValidationError"],
            activity_queues={
                "act_llm_gen_text": ActivityRouteConfig(
                    default="anthropic_q",
                    handle_options={
                        "claude-opus-4-7-1m": HandleOptions(
                            retry_policy_config=RetryPolicyConfig(
                                initial_interval=timedelta(seconds=3),
                                backoff_coefficient=2.0,
                                maximum_interval="unlimited",
                                maximum_attempts=3,
                                non_retryable_error_types_extra=["HandleSpecificError"],
                            ),
                        ),
                    },
                ),
            },
        )
        queue_options = {
            "anthropic_q": QueueOptions(
                retry_policy_config=RetryPolicyConfig(
                    initial_interval=timedelta(seconds=5),
                    backoff_coefficient=2.0,
                    maximum_interval="unlimited",
                    maximum_attempts=6,
                    non_retryable_error_types_extra=["AnthropicBadRequestError", "ValidationError"],
                ),
            ),
        }

        dispatch = worker_config.resolve_dispatch(
            activity_name="act_llm_gen_text",
            routing_key="claude-opus-4-7-1m",
            queue_options_by_queue=queue_options,
        )

        non_retryable = dispatch.retry_policy.non_retryable_error_types
        assert non_retryable is not None
        # Set equality — same contents regardless of order — plus length check to
        # verify deduplication actually fires (queue layer repeats ValidationError).
        assert set(non_retryable) == {
            "ValidationError",
            "AnthropicBadRequestError",
            "HandleSpecificError",
        }
        assert len(non_retryable) == 3

    def test_queue_options_partial_overlay(self) -> None:
        """Unset fields in ``QueueOptions`` (None) MUST NOT clobber the baseline
        — only explicit values overlay.
        """
        worker_config = _make_worker_config(
            baseline_heartbeat=timedelta(minutes=1),
            activity_queues={
                "act_llm_gen_text": ActivityRouteConfig(default="anthropic_q"),
            },
        )
        queue_options = {
            # Only start_to_close_timeout is set; heartbeat_timeout must fall through.
            "anthropic_q": QueueOptions(start_to_close_timeout=timedelta(minutes=5)),
        }

        dispatch = worker_config.resolve_dispatch(
            activity_name="act_llm_gen_text",
            routing_key="claude-opus-4-7",
            queue_options_by_queue=queue_options,
        )

        assert dispatch.start_to_close_timeout == timedelta(minutes=5)
        assert dispatch.heartbeat_timeout == timedelta(minutes=1)

    def test_overlay_rejects_baseline_non_retryable(self) -> None:
        """Overlay layers (``QueueOptions`` / ``HandleOptions``) must reject
        non-empty ``non_retryable_error_types`` on their nested retry policy
        — overlay contributions go through ``..._extra`` to make the additive
        composition rule unambiguous from the config alone.
        """
        with pytest.raises(ValidationError) as exc_info:
            QueueOptions(
                retry_policy_config=RetryPolicyConfig(
                    initial_interval=timedelta(seconds=3),
                    backoff_coefficient=2.0,
                    maximum_interval="unlimited",
                    maximum_attempts=3,
                    non_retryable_error_types=["BadError"],
                ),
            )
        assert "non_retryable_error_types_extra" in str(exc_info.value)

        with pytest.raises(ValidationError) as handle_exc_info:
            HandleOptions(
                retry_policy_config=RetryPolicyConfig(
                    initial_interval=timedelta(seconds=3),
                    backoff_coefficient=2.0,
                    maximum_interval="unlimited",
                    maximum_attempts=3,
                    non_retryable_error_types=["BadError"],
                ),
            )
        assert "non_retryable_error_types_extra" in str(handle_exc_info.value)

    def test_resolve_queue_still_works(self) -> None:
        """``resolve_queue`` must remain a thin delegate consistent with
        ``resolve_dispatch``'s queue resolution. Regression guard for callers
        that only need the queue name.
        """
        worker_config = _make_worker_config(
            activity_queues={
                "act_llm_gen_text": ActivityRouteConfig(
                    default="inference_q",
                    by_handle={"claude-opus-4-7": "anthropic_q"},
                ),
            },
        )

        # Per-handle wins.
        assert worker_config.resolve_queue("act_llm_gen_text", routing_key="claude-opus-4-7") == "anthropic_q"
        # Activity default for unmapped handle.
        assert worker_config.resolve_queue("act_llm_gen_text", routing_key="gpt-5") == "inference_q"
        # Worker default for unmapped activity.
        assert worker_config.resolve_queue("act_jinja2_gen_text") == "default_q"

        # resolve_dispatch agrees with resolve_queue on the queue name.
        assert worker_config.resolve_dispatch("act_llm_gen_text", "claude-opus-4-7").task_queue == "anthropic_q"
        assert worker_config.resolve_dispatch("act_llm_gen_text", "gpt-5").task_queue == "inference_q"
        assert worker_config.resolve_dispatch("act_jinja2_gen_text").task_queue == "default_q"
