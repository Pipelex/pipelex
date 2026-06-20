"""Unit tests for ``WorkerConfig.resolve_queue`` — the per-activity, per-handle
routing resolver introduced in v1, with the hybrid empty-routing fallback
added in v2.

Covers the resolution layers:
  0. Empty ``activity_queues`` (no routing configured) → ``None``, signalling
     the dispatch path to omit ``task_queue`` so Temporal uses the workflow's
     own queue (supports ``with_conditional_worker`` test isolation).
  1. Non-empty ``activity_queues``, unmapped activity → worker-wide
     ``default_task_queue``.
  2. Mapped activity, unmapped handle (or ``routing_key=None``) → activity ``default``.
  3. Mapped activity, mapped handle → per-handle queue.
"""

from datetime import timedelta

import pytest

from pipelex.system.configuration.config_temporal import ActivityRouteConfig, RetryPolicyConfig, WorkerConfig


def _make_worker_config(activity_queues: dict[str, ActivityRouteConfig] | None = None) -> WorkerConfig:
    """Build a minimal ``WorkerConfig`` for resolver tests.

    Only the fields read by ``resolve_queue`` matter here; the rest are filled
    with placeholder values that satisfy the schema.
    """
    return WorkerConfig(
        default_task_queue="default_q",
        activity_queues=activity_queues or {},
        workflow_execution_timeout=timedelta(hours=1),
        default_activity_start_to_close_timeout=timedelta(minutes=10),
        retry_policy_config=RetryPolicyConfig(
            initial_interval=timedelta(seconds=3),
            backoff_coefficient=2.0,
            maximum_interval="unlimited",
            maximum_attempts=3,
            non_retryable_error_types=[],
        ),
    )


class TestWorkerConfigResolveQueue:
    """Hybrid empty-routing fallback + three-layer resolution when routing is configured."""

    def test_empty_activity_queues_returns_none_for_workflow_local_dispatch(self) -> None:
        """When ``activity_queues`` is fully empty (default config, no routing
        configured), ``resolve_queue`` returns ``None`` so the dispatch path
        omits ``task_queue`` and Temporal routes the activity to the workflow's
        own queue. Required by ``with_conditional_worker`` and by the pre-v1
        default behavior.
        """
        worker_config = _make_worker_config()
        assert worker_config.resolve_queue("act_llm_gen_text", routing_key="claude-opus-4-7") is None
        assert worker_config.resolve_queue("act_some_unknown_activity") is None

    def test_unmapped_activity_with_non_empty_routing_falls_back_to_default_task_queue(self) -> None:
        """When the operator has configured routing for some activity, an
        unmapped activity still falls back explicitly to ``default_task_queue``.
        The empty-vs-non-empty distinction is the hybrid fallback hinge.
        """
        worker_config = _make_worker_config(
            {
                "act_img_gen_images": ActivityRouteConfig(default="img_q"),
            },
        )
        assert worker_config.resolve_queue("act_llm_gen_text", routing_key="claude-opus-4-7") == "default_q"
        assert worker_config.resolve_queue("act_some_unknown_activity") == "default_q"

    def test_mapped_activity_unmapped_handle_falls_back_to_activity_default(self) -> None:
        """When the activity is mapped but the handle does not match any
        ``by_handle`` entry, the activity-level ``default`` queue applies.
        """
        worker_config = _make_worker_config(
            {
                "act_llm_gen_text": ActivityRouteConfig(
                    default="inference_q",
                    by_handle={"claude-opus-4-7": "anthropic_q"},
                ),
            },
        )
        assert worker_config.resolve_queue("act_llm_gen_text", routing_key="gpt-5") == "inference_q"

    def test_mapped_activity_none_routing_key_uses_activity_default(self) -> None:
        """When the caller passes ``routing_key=None`` (non-handle activities
        like jinja2 or render-page-views), the activity-level ``default`` is
        used — ``by_handle`` is never consulted.
        """
        worker_config = _make_worker_config(
            {
                "act_render_page_views": ActivityRouteConfig(
                    default="render_q",
                    by_handle={"some-handle": "should_not_be_used_q"},
                ),
            },
        )
        assert worker_config.resolve_queue("act_render_page_views", routing_key=None) == "render_q"

    def test_mapped_activity_and_handle_uses_per_handle_queue(self) -> None:
        """When both the activity and the handle are mapped, the per-handle
        queue wins over the activity default.
        """
        worker_config = _make_worker_config(
            {
                "act_llm_gen_text": ActivityRouteConfig(
                    default="inference_q",
                    by_handle={
                        "claude-opus-4-7": "anthropic_q",
                        "gpt-5": "openai_q",
                    },
                ),
            },
        )
        assert worker_config.resolve_queue("act_llm_gen_text", routing_key="claude-opus-4-7") == "anthropic_q"
        assert worker_config.resolve_queue("act_llm_gen_text", routing_key="gpt-5") == "openai_q"

    @pytest.mark.parametrize(
        ("activity_name", "routing_key", "expected_queue"),
        [
            # Image generation routed by handle (e.g. provider grouping).
            ("act_img_gen_images", "flux-1.1-pro", "fal_q"),
            ("act_img_gen_images", "dall-e-3", "openai_image_q"),
            ("act_img_gen_images", "unknown-model", "image_gen_q"),
            # Extract routed by backend handle.
            ("act_extract_gen_extract_pages", "mistral-ocr", "mistral_extract_q"),
            ("act_extract_gen_extract_pages", "azure-ocr", "extract_q"),
            # Non-mapped activity stays on the default.
            ("act_jinja2_gen_text", None, "default_q"),
        ],
    )
    def test_realistic_routing_table_matrix(self, activity_name: str, routing_key: str | None, expected_queue: str) -> None:
        """Exercise a representative routing table with multiple activities and handles."""
        worker_config = _make_worker_config(
            {
                "act_img_gen_images": ActivityRouteConfig(
                    default="image_gen_q",
                    by_handle={
                        "flux-1.1-pro": "fal_q",
                        "dall-e-3": "openai_image_q",
                    },
                ),
                "act_extract_gen_extract_pages": ActivityRouteConfig(
                    default="extract_q",
                    by_handle={"mistral-ocr": "mistral_extract_q"},
                ),
            },
        )
        assert worker_config.resolve_queue(activity_name, routing_key=routing_key) == expected_queue
