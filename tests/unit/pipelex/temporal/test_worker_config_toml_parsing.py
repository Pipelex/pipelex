"""Unit test for ``activity_queues`` TOML parsing into ``WorkerConfig``.

The resolver tests in ``test_worker_config_resolve_queue.py`` construct
``WorkerConfig`` directly from Python kwargs — that does NOT exercise the
config-loading boundary (Pydantic parsing of a TOML-shaped dict). This test
closes that gap: it loads a TOML string with a representative
``activity_queues`` table and asserts that:

  - ``activity_queues`` materializes as ``dict[str, ActivityRouteConfig]``.
  - Per-activity ``default`` and per-handle ``by_handle`` survive parsing.
  - ``resolve_queue`` on the parsed config returns the expected queues.

This is the regression guard for the commented-out examples shipped in
``pipelex/pipelex.toml`` and ``pipelex/kit/configs/pipelex.toml``: if a
schema change ever breaks how operators are invited to override routing
in their projects, this test fails before the broken config reaches them.
"""

from datetime import timedelta

import tomli

from pipelex.system.configuration.config_temporal import ActivityRouteConfig, HandleOptions, RetryPolicyConfig, RetryPolicyConfigOverlay, WorkerConfig

_TOML_FRAGMENT = """
default_task_queue = "temporal_task_queue"
workflow_execution_timeout = "1:00:00"
run_timeout = "1:00:00"
task_timeout = "0:00:10"
start_delay = "0:00:00"
rpc_timeout = "1:00:00"
default_activity_start_to_close_timeout = "0:10:00"

[activity_queues.act_llm_gen_text]
default = "inference_q"
by_handle = { "claude-opus-4-7" = "anthropic_q", "gpt-5" = "openai_q" }

[activity_queues.act_llm_gen_text.handle_options."claude-opus-4-7-1m"]
start_to_close_timeout = "0:25:00"

[activity_queues.act_img_gen_images]
default = "image_gen_q"
by_handle = { "flux-1.1-pro" = "fal_q" }

[activity_queues.act_extract_gen_extract_pages]
default = "extract_q"
by_handle = {}

[retry_policy_config]
initial_interval = "0:00:03"
backoff_coefficient = 2.0
maximum_interval = "unlimited"
maximum_attempts = 3
non_retryable_error_types = []
"""


class TestWorkerConfigTomlParsing:
    """Parse a TOML fragment shaped like the project override and validate
    that the new per-activity routing keys (including ``handle_options``) round-trip into ``WorkerConfig``.
    """

    def test_activity_queues_parse_into_typed_models(self) -> None:
        worker_config = WorkerConfig.model_validate(tomli.loads(_TOML_FRAGMENT))

        assert worker_config.default_task_queue == "temporal_task_queue"
        assert set(worker_config.activity_queues.keys()) == {
            "act_llm_gen_text",
            "act_img_gen_images",
            "act_extract_gen_extract_pages",
        }
        for route in worker_config.activity_queues.values():
            assert isinstance(route, ActivityRouteConfig)

        llm_route = worker_config.activity_queues["act_llm_gen_text"]
        assert llm_route.default == "inference_q"
        assert llm_route.by_handle == {"claude-opus-4-7": "anthropic_q", "gpt-5": "openai_q"}
        # handle_options round-trip into HandleOptions models.
        assert set(llm_route.handle_options.keys()) == {"claude-opus-4-7-1m"}
        opus_1m = llm_route.handle_options["claude-opus-4-7-1m"]
        assert isinstance(opus_1m, HandleOptions)
        assert opus_1m.start_to_close_timeout == timedelta(minutes=25)

        img_route = worker_config.activity_queues["act_img_gen_images"]
        assert img_route.default == "image_gen_q"
        assert img_route.by_handle == {"flux-1.1-pro": "fal_q"}
        # handle_options defaults to an empty dict when omitted from TOML.
        assert img_route.handle_options == {}

        extract_route = worker_config.activity_queues["act_extract_gen_extract_pages"]
        assert extract_route.default == "extract_q"
        assert extract_route.by_handle == {}

    def test_resolve_queue_works_on_parsed_config(self) -> None:
        """End-to-end: parse the TOML, then dispatch through ``resolve_queue``."""
        worker_config = WorkerConfig.model_validate(tomli.loads(_TOML_FRAGMENT))

        # Layer 3: per-handle override wins.
        assert worker_config.resolve_queue("act_llm_gen_text", routing_key="claude-opus-4-7") == "anthropic_q"
        assert worker_config.resolve_queue("act_llm_gen_text", routing_key="gpt-5") == "openai_q"
        # Layer 2: unmapped handle falls back to the activity default.
        assert worker_config.resolve_queue("act_llm_gen_text", routing_key="some-other-model") == "inference_q"
        # Layer 2 again: routing_key=None on a mapped activity uses its default
        # without ever consulting by_handle.
        assert worker_config.resolve_queue("act_extract_gen_extract_pages", routing_key=None) == "extract_q"
        # Layer 1: completely unmapped activity falls back to the worker default.
        assert worker_config.resolve_queue("act_jinja2_gen_text") == "temporal_task_queue"

    def test_retry_policy_finite_maximum_interval_from_toml(self) -> None:
        """Finite TOML duration on ``maximum_interval`` must round-trip under
        ``ConfigModel``'s ``strict=True``. Regression for the missing ``strict=False``
        on the Annotated arm of the Union — without it, operator overlays like
        ``maximum_interval = "0:02:00"`` blocked config load.
        """
        toml_fragment = """
initial_interval = "0:00:03"
backoff_coefficient = 2.0
maximum_interval = "0:02:00"
maximum_attempts = 3
non_retryable_error_types = []
"""
        baseline = RetryPolicyConfig.model_validate(tomli.loads(toml_fragment))
        assert baseline.maximum_interval == timedelta(minutes=2)

        # Same on the overlay class — both inherit RetryPolicyConfigBase, so the
        # fix at the base must cover both layers.
        overlay_fragment = """
initial_interval = "0:00:03"
backoff_coefficient = 2.0
maximum_interval = "0:02:00"
maximum_attempts = 3
non_retryable_error_types_extra = []
"""
        overlay = RetryPolicyConfigOverlay.model_validate(tomli.loads(overlay_fragment))
        assert overlay.maximum_interval == timedelta(minutes=2)
