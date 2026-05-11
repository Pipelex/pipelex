"""Unit tests for ``WorkerConfig.resolve_queue`` — the per-activity, per-handle
routing resolver introduced in v1.

Covers the three resolution layers:
  1. Unmapped activity → worker-wide default ``task_queue``.
  2. Mapped activity, unmapped handle (or ``routing_key=None``) → activity ``default``.
  3. Mapped activity, mapped handle → per-handle queue.
"""

from datetime import timedelta

import pytest

from pipelex.temporal.config_temporal import ActivityRouteConfig, RetryPolicyConfig, WorkerConfig


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
    """Three-layer resolution: per-handle → per-activity default → worker default."""

    def test_unmapped_activity_falls_back_to_default_task_queue(self) -> None:
        """An activity not present in ``activity_queues`` must use ``task_queue``."""
        worker_config = _make_worker_config()
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
