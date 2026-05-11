"""Unit tests for the ``is_traced`` argument to ``WorkerConfig.resolve_dispatch``.

Tracing emits one log line per dispatch with the resolved queue +
start_to_close_timeout + retry attempts and the layer each scalar came from
(``baseline`` / ``queue_options`` / ``handle_options``). Off by default.
"""

import logging
from datetime import timedelta

import pytest

from pipelex.temporal.config_temporal import (
    ActivityRouteConfig,
    HandleOptions,
    QueueOptions,
    RetryPolicyConfig,
    WorkerConfig,
)


def _make_worker_config(activity_queues: dict[str, ActivityRouteConfig] | None = None) -> WorkerConfig:
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


class TestDispatchResolutionTracing:
    """``is_traced=True`` emits a structured log line with from= layer info."""

    def test_off_emits_no_log(self, caplog: pytest.LogCaptureFixture) -> None:
        """With ``is_traced=False`` (default), no trace log line is emitted."""
        worker_config = _make_worker_config()
        with caplog.at_level(logging.INFO):
            worker_config.resolve_dispatch(activity_name="act_llm_gen_text", routing_key="claude-opus-4-7")
        trace_records = [record for record in caplog.records if "temporal.dispatch" in record.message]
        assert not trace_records, f"trace log fired when is_traced=False: {[r.message for r in trace_records]!r}"

    def test_baseline_source_when_no_overrides(self, caplog: pytest.LogCaptureFixture) -> None:
        """No queue_options / no handle_options → ``from=baseline`` on every scalar."""
        worker_config = _make_worker_config()
        with caplog.at_level(logging.INFO):
            worker_config.resolve_dispatch(activity_name="act_llm_gen_text", routing_key="claude-opus-4-7", is_traced=True)
        trace_records = [record for record in caplog.records if "temporal.dispatch" in record.message]
        assert len(trace_records) == 1, f"expected exactly one trace line, got {len(trace_records)}"
        line = trace_records[0].message
        assert "act=act_llm_gen_text" in line
        assert "handle=claude-opus-4-7" in line
        assert "queue=default_q" in line
        # Baseline 10-minute timeout = 600s.
        assert "timeout=600.0s" in line
        assert "(from=baseline)" in line

    def test_queue_options_source(self, caplog: pytest.LogCaptureFixture) -> None:
        """When ``queue_options[X].start_to_close_timeout`` overrides baseline,
        the trace line reports ``from=queue_options`` for the timeout column.
        """
        worker_config = _make_worker_config(
            activity_queues={"act_llm_gen_text": ActivityRouteConfig(default="anthropic_q", by_handle={})},
        )
        queue_options = {"anthropic_q": QueueOptions(start_to_close_timeout=timedelta(minutes=5))}
        with caplog.at_level(logging.INFO):
            worker_config.resolve_dispatch(
                activity_name="act_llm_gen_text",
                routing_key="some-handle",
                queue_options_by_queue=queue_options,
                is_traced=True,
            )
        trace_records = [record for record in caplog.records if "temporal.dispatch" in record.message]
        assert len(trace_records) == 1
        line = trace_records[0].message
        assert "queue=anthropic_q" in line
        assert "timeout=300.0s (from=queue_options)" in line

    def test_handle_options_source_wins(self, caplog: pytest.LogCaptureFixture) -> None:
        """When ``handle_options.start_to_close_timeout`` is set, the trace
        reports ``from=handle_options`` even if ``queue_options`` also had one.
        """
        worker_config = _make_worker_config(
            activity_queues={
                "act_llm_gen_text": ActivityRouteConfig(
                    default="anthropic_q",
                    by_handle={},
                    handle_options={"claude-opus-4-7-1m": HandleOptions(start_to_close_timeout=timedelta(minutes=25))},
                ),
            },
        )
        queue_options = {"anthropic_q": QueueOptions(start_to_close_timeout=timedelta(minutes=5))}
        with caplog.at_level(logging.INFO):
            worker_config.resolve_dispatch(
                activity_name="act_llm_gen_text",
                routing_key="claude-opus-4-7-1m",
                queue_options_by_queue=queue_options,
                is_traced=True,
            )
        trace_records = [record for record in caplog.records if "temporal.dispatch" in record.message]
        assert len(trace_records) == 1
        line = trace_records[0].message
        assert "timeout=1500.0s (from=handle_options)" in line
