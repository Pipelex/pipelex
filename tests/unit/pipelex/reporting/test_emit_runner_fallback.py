"""Tests for the runner-side activity event log fallback in ReportingManager._emit_usage_event.

Pins the behavior introduced in Phase 2 of the cross-worker tracing P0 plan:
when context lookup misses (runner process never had set_event_log called for
this workflow), the manager emits the usage event through a per-process
activity event log instead of dropping silently.
"""

import logging
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from botocore.exceptions import ClientError
from pytest_mock import MockerFixture

from pipelex.base_exceptions import PipelexConfigError
from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.cogt.llm.llm_job_components import LLMJobConfig, LLMJobParams, LLMJobReport
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.cogt.llm.llm_report import LLMTokensUsage
from pipelex.cogt.usage.cost_category import CostCategory
from pipelex.cogt.usage.token_category import TokenCategory
from pipelex.config import get_config
from pipelex.graph.graph_config import DataInclusionConfig
from pipelex.graph.trace_context import TraceContext
from pipelex.pipeline.job_metadata import JobMetadata, UnitJobId
from pipelex.reporting.reporting_manager import ReportingManager
from pipelex.system.configuration.configs import NdjsonTracingConfig, TracingBackend
from pipelex.system.exceptions import MissingDependencyError
from pipelex.tracing import activity_event_log
from pipelex.tracing.activity_event_log import ActivityEventLogCache
from pipelex.tracing.in_memory_event_log import InMemoryEventLog
from pipelex.tracing.ndjson_event_log import NdjsonEventLog
from pipelex.tracing.trace_events import UsageReportEvent

DATA_INCLUSION_OFF = DataInclusionConfig(
    pipe_and_concept_registry=False,
    stuff_json_content=False,
    stuff_text_content=False,
    stuff_html_content=False,
    error_stack_traces=False,
)


def _make_llm_job(
    pipeline_run_id: str,
    trace_context: TraceContext | None,
    nb_input_tokens: int = 100,
    nb_output_tokens: int = 50,
) -> LLMJob:
    now = datetime.now(timezone.utc)
    job_metadata = JobMetadata(
        user_id="test_user",
        pipeline_run_id=pipeline_run_id,
        trace_context=trace_context,
        started_at=now,
        completed_at=now + timedelta(seconds=1),
        unit_job_id=UnitJobId.LLM_GEN_TEXT,
    )
    tokens_usage = LLMTokensUsage(
        job_metadata=job_metadata,
        inference_model_name="test-model",
        inference_model_id="test-model-id",
        unit_costs={CostCategory.INPUT: 1.0, CostCategory.OUTPUT: 2.0},
        nb_tokens_by_category={TokenCategory.INPUT: nb_input_tokens, TokenCategory.OUTPUT: nb_output_tokens},
    )
    return LLMJob(
        job_metadata=job_metadata,
        llm_prompt=LLMPrompt(),
        job_params=LLMJobParams(temperature=0.5),
        job_config=LLMJobConfig(schema_reask_max_attempts=1),
        job_report=LLMJobReport(llm_tokens_usage=tokens_usage),
    )


def _make_trace_context(
    graph_id: str,
    parent_node_id: str | None = "g:node_0",
    tracer_key: str | None = None,
) -> TraceContext:
    return TraceContext(
        graph_id=graph_id,
        tracer_key=tracer_key,
        parent_node_id=parent_node_id,
        node_sequence=0,
        data_inclusion=DATA_INCLUSION_OFF,
    )


@pytest.fixture(autouse=True)
def _reset_activity_event_log_state() -> Any:  # pyright: ignore[reportUnusedFunction]
    """Class-level state on ActivityEventLogCache persists across tests; reset it."""
    ActivityEventLogCache.reset_for_tests()
    yield
    ActivityEventLogCache.reset_for_tests()


def _enable_ndjson_tracing(mocker: MockerFixture, traces_dir: Path) -> None:
    """Patch the live tracing config to enabled NDJSON pointing at traces_dir."""
    cfg = get_config().pipelex.tracing_config
    mocker.patch.object(cfg, "is_enabled", True)
    mocker.patch.object(cfg, "backend", TracingBackend.NDJSON)
    mocker.patch.object(cfg, "ndjson", NdjsonTracingConfig(traces_dir=str(traces_dir)))


class TestEmitRunnerFallback:
    """Pins the runner-side fallback emission contract."""

    def test_fallback_engages_when_context_missing_and_tracing_enabled(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
    ) -> None:
        """When set_event_log is never called and tracing is enabled, the fallback emits an NDJSON usage event."""
        _enable_ndjson_tracing(mocker, tmp_path)

        manager = ReportingManager()
        manager.setup()
        trace_context = _make_trace_context(graph_id="run_abc", tracer_key="wf_xyz", parent_node_id="g:node_2")
        llm_job = _make_llm_job("run_abc", trace_context=trace_context)

        manager.report_inference_job(llm_job)

        run_dir = tmp_path / "run_abc"
        ndjson_files = list(run_dir.glob("*.ndjson"))
        assert len(ndjson_files) == 1
        assert ndjson_files[0].name.startswith("wf_wf_xyz__w_act_"), ndjson_files[0].name

        reader = NdjsonEventLog(traces_dir=str(tmp_path))
        events = reader.read_events("run_abc")
        usage_events = [evt for evt in events if isinstance(evt, UsageReportEvent)]
        assert len(usage_events) == 1
        assert usage_events[0].workflow_id == "wf_xyz"
        assert usage_events[0].pipeline_run_id == "run_abc"
        assert usage_events[0].node_id == "g:node_2"
        assert usage_events[0].writer_id.startswith("act_")

    def test_runner_fallback_uses_tracer_key_when_set(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
    ) -> None:
        """workflow_id on the emitted event is trace_context.tracer_key when set, else graph_id."""
        _enable_ndjson_tracing(mocker, tmp_path)

        manager = ReportingManager()
        manager.setup()

        # Case 1: tracer_key set → workflow_id == tracer_key
        ctx_with_tracer = _make_trace_context(graph_id="run_abc", tracer_key="wf_xyz")
        manager.report_inference_job(_make_llm_job("run_abc", trace_context=ctx_with_tracer))

        # Case 2: tracer_key None → workflow_id == graph_id
        ctx_no_tracer = _make_trace_context(graph_id="run_def", tracer_key=None)
        manager.report_inference_job(_make_llm_job("run_def", trace_context=ctx_no_tracer))

        reader = NdjsonEventLog(traces_dir=str(tmp_path))
        events_abc = [evt for evt in reader.read_events("run_abc") if isinstance(evt, UsageReportEvent)]
        events_def = [evt for evt in reader.read_events("run_def") if isinstance(evt, UsageReportEvent)]

        assert len(events_abc) == 1
        assert events_abc[0].workflow_id == "wf_xyz"
        assert len(events_def) == 1
        assert events_def[0].workflow_id == "run_def"

    def test_fallback_caches_event_log_per_process(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
    ) -> None:
        """make_event_log is called only once per process — the second emission reuses the cached log."""
        _enable_ndjson_tracing(mocker, tmp_path)
        spy = mocker.spy(activity_event_log, "make_event_log")

        manager = ReportingManager()
        manager.setup()
        trace_context = _make_trace_context(graph_id="run_abc", tracer_key="wf_xyz")

        manager.report_inference_job(_make_llm_job("run_abc", trace_context=trace_context))
        manager.report_inference_job(_make_llm_job("run_abc", trace_context=trace_context))

        assert spy.call_count == 1

    def test_concurrent_first_call_yields_single_writer_id(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
    ) -> None:
        """Concurrent first-callers from N threads observe the same writer_id and event log instance.

        Pins the threading.Lock fix: without double-checked locking, two threads could each
        construct their own backend, generating two writer_ids and racing on the file.
        """
        _enable_ndjson_tracing(mocker, tmp_path)
        cfg = get_config().pipelex.tracing_config

        nb_threads = 16
        barrier = threading.Barrier(nb_threads)
        seen_logs: list[Any] = []
        seen_lock = threading.Lock()

        def call_fn() -> None:
            barrier.wait()
            log_instance = ActivityEventLogCache.get_or_create(cfg)
            with seen_lock:
                seen_logs.append(log_instance)

        threads = [threading.Thread(target=call_fn) for _ in range(nb_threads)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)

        assert len(seen_logs) == nb_threads
        # All threads must observe the same backend instance and writer_id.
        for log_instance in seen_logs:
            assert log_instance is seen_logs[0]
        writer_ids = {log_instance.writer_id for log_instance in seen_logs}
        assert len(writer_ids) == 1

    def test_disabled_tracing_skips_emit(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
    ) -> None:
        """When tracing_config.is_enabled=False, the fallback returns without writing any file."""
        cfg = get_config().pipelex.tracing_config
        mocker.patch.object(cfg, "is_enabled", False)

        manager = ReportingManager()
        manager.setup()
        trace_context = _make_trace_context(graph_id="run_silent", tracer_key="wf_silent")

        manager.report_inference_job(_make_llm_job("run_silent", trace_context=trace_context))

        # No NDJSON files should have been created.
        assert list(tmp_path.glob("**/*.ndjson")) == []

    def test_no_trace_context_skips_emit(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
    ) -> None:
        """When job_metadata.trace_context is None, neither fast path nor fallback engages."""
        _enable_ndjson_tracing(mocker, tmp_path)

        manager = ReportingManager()
        manager.setup()

        manager.report_inference_job(_make_llm_job("run_abc", trace_context=None))

        assert list(tmp_path.glob("**/*.ndjson")) == []

    @pytest.mark.parametrize(
        ("exc_type", "exc_args"),
        [
            (OSError, ("disk full",)),
            (MissingDependencyError, ("boto3", "dynamodb")),
            (PipelexConfigError, ("misconfigured",)),
        ],
        ids=["oserror", "missing_dep", "config_error"],
    )
    def test_explicit_log_when_emit_path_unavailable(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
        caplog: pytest.LogCaptureFixture,
        exc_type: type[BaseException],
        exc_args: tuple[Any, ...],
    ) -> None:
        """Specific exception types from make_event_log are caught, logged WARNING, and dropped.

        Implementation must NOT use except Exception; each type is named explicitly.
        """
        _enable_ndjson_tracing(mocker, tmp_path)
        mocker.patch(
            "pipelex.tracing.activity_event_log.make_event_log",
            side_effect=exc_type(*exc_args),
        )

        manager = ReportingManager()
        manager.setup()
        trace_context = _make_trace_context(graph_id="run_abc", tracer_key="wf_xyz")

        with caplog.at_level(logging.WARNING):
            # Must not raise — the failure is logged and dropped.
            manager.report_inference_job(_make_llm_job("run_abc", trace_context=trace_context))

        assert any(record.levelno == logging.WARNING for record in caplog.records)

    def test_explicit_log_when_emit_raises_client_error(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """A botocore ClientError raised by event_log.emit() is caught, logged WARNING, and dropped."""
        _enable_ndjson_tracing(mocker, tmp_path)

        # Force the event log to raise ClientError on emit.
        stub_log = InMemoryEventLog(writer_id="act_test")
        client_error = ClientError(
            error_response={"Error": {"Code": "ProvisionedThroughputExceededException"}},
            operation_name="PutItem",
        )
        mocker.patch.object(stub_log, "emit", side_effect=client_error)
        mocker.patch(
            "pipelex.tracing.activity_event_log.make_event_log",
            return_value=stub_log,
        )

        manager = ReportingManager()
        manager.setup()
        trace_context = _make_trace_context(graph_id="run_abc", tracer_key="wf_xyz")

        with caplog.at_level(logging.WARNING):
            manager.report_inference_job(_make_llm_job("run_abc", trace_context=trace_context))

        assert any(record.levelno == logging.WARNING for record in caplog.records)

    def test_warning_emitted_once_per_process_when_fallback_engages(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """The 'runner fallback engaged' warning fires only on the first emission per process."""
        _enable_ndjson_tracing(mocker, tmp_path)

        manager = ReportingManager()
        manager.setup()
        trace_context = _make_trace_context(graph_id="run_abc", tracer_key="wf_xyz")

        with caplog.at_level(logging.WARNING):
            for _ in range(100):
                manager.report_inference_job(_make_llm_job("run_abc", trace_context=trace_context))

        engaged_records = [record for record in caplog.records if "runner-side" in record.message.lower()]
        assert len(engaged_records) == 1

    def test_warning_emitted_once_even_with_multiple_managers(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Module-level once-flag survives multiple ReportingManager instances."""
        _enable_ndjson_tracing(mocker, tmp_path)

        trace_context = _make_trace_context(graph_id="run_abc", tracer_key="wf_xyz")

        with caplog.at_level(logging.WARNING):
            manager_a = ReportingManager()
            manager_a.setup()
            manager_a.report_inference_job(_make_llm_job("run_abc", trace_context=trace_context))

            manager_b = ReportingManager()
            manager_b.setup()
            manager_b.report_inference_job(_make_llm_job("run_abc", trace_context=trace_context))

        engaged_records = [record for record in caplog.records if "runner-side" in record.message.lower()]
        assert len(engaged_records) == 1

    def test_retried_activity_emits_duplicate_usage_event_documenting_r2(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
    ) -> None:
        """Pins R2: retried activities re-emit; today's behavior is two events at sequence N and N+1.

        Documents over-counting risk and prevents silent regression of this contract.
        """
        _enable_ndjson_tracing(mocker, tmp_path)

        manager = ReportingManager()
        manager.setup()
        trace_context = _make_trace_context(graph_id="run_abc", tracer_key="wf_xyz")

        manager.report_inference_job(_make_llm_job("run_abc", trace_context=trace_context))
        manager.report_inference_job(_make_llm_job("run_abc", trace_context=trace_context))

        reader = NdjsonEventLog(traces_dir=str(tmp_path))
        events = [evt for evt in reader.read_events("run_abc") if isinstance(evt, UsageReportEvent)]
        assert len(events) == 2
        assert sorted(evt.sequence for evt in events) == [0, 1]
