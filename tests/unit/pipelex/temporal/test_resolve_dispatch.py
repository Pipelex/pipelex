"""Unit tests for ``WorkerConfig.resolve_dispatch`` — the submitter-side
resolution chain that returns a ``DispatchOptions`` bundle for every
``workflow.execute_activity(...)`` call.

Covers the three layering layers (baseline → queue_options → handle_options)
for scalars (last-wins), the additive composition of
``non_retryable_error_types``, the hybrid empty-routing fallback that omits
``task_queue`` so Temporal uses the workflow's own queue, and the layer-aware
split between baseline ``RetryPolicyConfig`` and overlay
``RetryPolicyConfigOverlay`` enforced by Pydantic's ``extra="forbid"``.
"""

from datetime import timedelta

import pytest
from pydantic import ValidationError

from pipelex.system.configuration.config_temporal import (
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
        non_retryable_error_types=non_retryable or ["ValidationError"],
    )


def _make_overlay_retry(
    non_retryable_extra: list[str] | None = None,
    maximum_attempts: int = 3,
    initial_interval_seconds: int = 3,
) -> RetryPolicyConfigOverlay:
    return RetryPolicyConfigOverlay(
        initial_interval=timedelta(seconds=initial_interval_seconds),
        backoff_coefficient=2.0,
        maximum_interval="unlimited",
        maximum_attempts=maximum_attempts,
        non_retryable_error_types_extra=non_retryable_extra or [],
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

    def test_empty_activity_queues_omits_task_queue_for_workflow_local_dispatch(self) -> None:
        """Hybrid fallback: with ``activity_queues`` empty (default config),
        ``resolve_dispatch`` returns ``task_queue=None`` and ``to_execute_kwargs``
        omits the key so Temporal routes to the workflow's own queue. Required
        by the ``with_conditional_worker`` test isolation pattern.
        """
        worker_config = _make_worker_config()

        dispatch = worker_config.resolve_dispatch(activity_name="act_llm_gen_text", routing_key="claude-opus-4-7")

        assert dispatch.task_queue is None
        kwargs = dispatch.to_execute_kwargs()
        assert "task_queue" not in kwargs
        assert "start_to_close_timeout" in kwargs
        assert "retry_policy" in kwargs

    def test_non_empty_activity_queues_unmapped_falls_back_to_default_task_queue(self) -> None:
        """When ``activity_queues`` is non-empty (operator opted into routing
        topology) but the queried activity isn't mapped, dispatch falls back
        explicitly to ``default_task_queue`` — operator clearly wants explicit
        routing, so we don't second-guess them.
        """
        worker_config = _make_worker_config(
            activity_queues={"act_img_gen_images": ActivityRouteConfig(default="img_q")},
        )

        dispatch = worker_config.resolve_dispatch(activity_name="act_llm_gen_text")

        assert dispatch.task_queue == "default_q"
        assert dispatch.to_execute_kwargs()["task_queue"] == "default_q"

    def test_mapped_activity_uses_baseline_when_no_overlay(self) -> None:
        """With routing pinning ``act_llm_gen_text`` to a specific queue but no
        ``queue_options`` overlay, dispatch produces that queue + baseline
        scalars verbatim, and ``to_execute_kwargs`` includes ``task_queue``.
        """
        worker_config = _make_worker_config(
            activity_queues={"act_llm_gen_text": ActivityRouteConfig(default="anthropic_q")},
        )

        dispatch = worker_config.resolve_dispatch(activity_name="act_llm_gen_text", routing_key="claude-opus-4-7")

        assert dispatch.task_queue == "anthropic_q"
        assert dispatch.start_to_close_timeout == timedelta(minutes=10)
        assert dispatch.heartbeat_timeout is None
        kwargs = dispatch.to_execute_kwargs()
        assert kwargs["task_queue"] == "anthropic_q"
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
                            retry_policy_config=_make_overlay_retry(
                                non_retryable_extra=["HandleSpecificError"],
                            ),
                        ),
                    },
                ),
            },
        )
        queue_options = {
            "anthropic_q": QueueOptions(
                retry_policy_config=_make_overlay_retry(
                    non_retryable_extra=["AnthropicBadRequestError", "ValidationError"],
                    maximum_attempts=6,
                    initial_interval_seconds=5,
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

    def test_split_classes_lock_in_extra_forbid(self) -> None:
        """The split-class invariant is load-bearing on ``ConfigModel``'s
        ``extra="forbid"`` setting: if ``extra="allow"`` were ever set on
        either subclass, the layer asymmetry would silently lift and the
        original silent-drop bug for baseline ``_extra`` would come back.
        Assert the setting directly so a future contributor flipping it gets
        a unit-test failure rather than a runtime regression.
        """
        assert RetryPolicyConfig.model_config.get("extra") == "forbid"
        assert RetryPolicyConfigOverlay.model_config.get("extra") == "forbid"

    def test_baseline_class_rejects_extra_field(self) -> None:
        """Issue #880 #5 regression: ``RetryPolicyConfig`` (baseline) has no
        ``non_retryable_error_types_extra`` field. ``ConfigModel``'s
        ``extra="forbid"`` raises if a user sets it on the baseline — preventing
        the silent-drop bug where baseline ``_extra`` entries never reach the
        merged non-retryable list at dispatch time.
        """
        with pytest.raises(ValidationError) as exc_info:
            RetryPolicyConfig.model_validate(
                {
                    "initial_interval": "0:00:03",
                    "backoff_coefficient": 2.0,
                    "maximum_interval": "unlimited",
                    "maximum_attempts": 3,
                    "non_retryable_error_types": [],
                    "non_retryable_error_types_extra": ["should_be_rejected"],
                },
            )
        assert "non_retryable_error_types_extra" in str(exc_info.value)

    def test_overlay_class_rejects_main_list_field(self) -> None:
        """Issue #880 #5 regression: ``RetryPolicyConfigOverlay`` has no
        ``non_retryable_error_types`` field. ``ConfigModel``'s ``extra="forbid"``
        raises if a user sets it on an overlay — overlays MUST contribute via
        ``_extra`` so the additive composition rule stays unambiguous from the
        config alone.
        """
        with pytest.raises(ValidationError) as exc_info:
            RetryPolicyConfigOverlay.model_validate(
                {
                    "initial_interval": "0:00:03",
                    "backoff_coefficient": 2.0,
                    "maximum_interval": "unlimited",
                    "maximum_attempts": 3,
                    "non_retryable_error_types": ["should_be_rejected"],
                },
            )
        assert "non_retryable_error_types" in str(exc_info.value)

    def test_queue_options_applies_via_default_task_queue_when_routing_empty(self) -> None:
        """Empty-routing hybrid fallback asymmetry: dispatch still emits
        ``task_queue=None`` (activities ride the workflow's own queue) but
        ``queue_options[default_task_queue]`` still applies so single-queue
        deployments can tune timeouts/retry/rate without opting into the
        ``activity_queues`` routing topology.
        """
        worker_config = _make_worker_config()  # empty activity_queues, default_task_queue="default_q"
        queue_options = {"default_q": QueueOptions(start_to_close_timeout=timedelta(minutes=5))}

        dispatch = worker_config.resolve_dispatch(
            activity_name="act_llm_gen_text",
            routing_key="claude-opus-4-7",
            queue_options_by_queue=queue_options,
        )

        # Dispatch still omits task_queue (workflow-local).
        assert dispatch.task_queue is None
        assert "task_queue" not in dispatch.to_execute_kwargs()
        # But the queue_options[default_task_queue] timeout overlay applies.
        assert dispatch.start_to_close_timeout == timedelta(minutes=5)

    def test_resolve_queue_still_works(self) -> None:
        """``resolve_queue`` must remain a thin delegate consistent with
        ``resolve_dispatch``'s queue resolution. Regression guard for callers
        that only need the queue name. Empty-routing returns None; non-empty
        routing uses the v1 three-layer resolution.
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
        # Worker default for unmapped activity (routing IS configured, so non-empty hybrid path).
        assert worker_config.resolve_queue("act_jinja2_gen_text") == "default_q"

        # resolve_dispatch agrees with resolve_queue on the queue name.
        assert worker_config.resolve_dispatch("act_llm_gen_text", routing_key="claude-opus-4-7").task_queue == "anthropic_q"
        assert worker_config.resolve_dispatch("act_llm_gen_text", routing_key="gpt-5").task_queue == "inference_q"
        assert worker_config.resolve_dispatch("act_jinja2_gen_text").task_queue == "default_q"
