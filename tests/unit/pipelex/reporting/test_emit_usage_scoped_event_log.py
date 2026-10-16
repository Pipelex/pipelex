import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from pytest_mock import MockerFixture

from pipelex.cogt.extract.extract_input import ExtractInput
from pipelex.cogt.extract.extract_job import ExtractJob
from pipelex.cogt.extract.extract_job_components import ExtractJobConfig, ExtractJobParams, ExtractJobReport
from pipelex.cogt.extract.extract_report import ExtractTokensUsage
from pipelex.cogt.img_gen.img_gen_job import ImgGenJob
from pipelex.cogt.img_gen.img_gen_job_components import AspectRatio, Background, ImgGenJobConfig, ImgGenJobParams, ImgGenJobReport
from pipelex.cogt.img_gen.img_gen_prompt import ImgGenPrompt
from pipelex.cogt.img_gen.img_gen_report import ImgGenTokensUsage
from pipelex.cogt.inference.inference_job_abstract import InferenceJobAbstract
from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.cogt.llm.llm_job_components import LLMJobConfig, LLMJobParams, LLMJobReport
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.cogt.llm.llm_report import LLMTokensUsage
from pipelex.cogt.usage.cost_category import CostCategory
from pipelex.cogt.usage.token_category import TokenCategory
from pipelex.config import get_config
from pipelex.reporting.reporting_manager import ReportingManager
from pipelex.runtime_hub import get_event_log_override, scoped_event_log
from pipelex.system.configuration.configs import NdjsonTracingConfig, TracingBackend
from pipelex.system.data_inclusion_config import DataInclusionConfig
from pipelex.system.execution_chain import ExecutionAttempt
from pipelex.system.job_metadata import JobMetadata, RunMetadata, UnitJobId
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.system.trace_context import TraceContext
from pipelex.tools.misc.image_utils import ImageFormat
from pipelex.tracing.activity_event_log import ActivityEventLogCache
from pipelex.tracing.in_memory_event_log import InMemoryEventLog
from pipelex.tracing.ndjson_event_log import NdjsonEventLog
from pipelex.tracing.trace_events import UsageReportEvent

_DATA_INCLUSION_OFF = DataInclusionConfig(
    pipe_and_concept_registry=False,
    stuff_json_content=False,
    error_stack_traces=False,
)

_ISOLATION_PROBE_TARGET = "pipelex.reporting.reporting_manager.is_in_isolated_execution"


def _trace_context(run_id: str, *, emit_usage_events: bool = True) -> TraceContext:
    """A trace context for a leaf of a dispatched workflow: its own attempt under the run's, at a known path."""
    return TraceContext(
        graph_id=run_id,
        tracer_key=f"wf_{run_id}",
        parent_node_id=f"{run_id}:node_3",
        node_sequence=3,
        data_inclusion=_DATA_INCLUSION_OFF,
        emit_usage_events=emit_usage_events,
        run_mode=PipeRunMode.LIVE,
        chain=[ExecutionAttempt(execution=f"wf_{run_id}", attempt=1), ExecutionAttempt(execution=f"wf_{run_id}--branch", attempt=2)],
        parent_path="method.main/step_2",
    )


def _job_metadata(run_id: str, *, emit_usage_events: bool = True, unit_job_id: UnitJobId | None = None) -> JobMetadata:
    now = datetime.now(UTC)
    return JobMetadata(
        run_metadata=RunMetadata(storage_scope="test/scope", read_scope=None, user_id="test_user", pipeline_run_id=run_id),
        trace_context=_trace_context(run_id, emit_usage_events=emit_usage_events),
        started_at=now,
        completed_at=now + timedelta(seconds=1),
        unit_job_id=unit_job_id,
    )


def _make_llm_job(run_id: str, *, emit_usage_events: bool = True) -> LLMJob:
    job_metadata = _job_metadata(run_id, emit_usage_events=emit_usage_events, unit_job_id=UnitJobId.LLM_GEN_TEXT)
    return LLMJob(
        job_metadata=job_metadata,
        llm_prompt=LLMPrompt(),
        job_params=LLMJobParams(temperature=0.5),
        job_config=LLMJobConfig(schema_reask_max_attempts=1),
        job_report=LLMJobReport(
            llm_tokens_usage=LLMTokensUsage(
                job_metadata=job_metadata,
                inference_model_name="llm-model",
                inference_model_id="llm-model-id",
                unit_costs={CostCategory.INPUT: 1.0, CostCategory.OUTPUT: 2.0},
                nb_tokens_by_category={TokenCategory.INPUT: 100, TokenCategory.OUTPUT: 50},
            )
        ),
    )


def _make_img_gen_job(run_id: str) -> ImgGenJob:
    job_metadata = _job_metadata(run_id)
    return ImgGenJob(
        img_gen_prompt=ImgGenPrompt(positive_text="a prompt"),
        job_params=ImgGenJobParams(
            aspect_ratio=AspectRatio.SQUARE,
            size=None,
            background=Background.OPAQUE,
            input_fidelity=None,
            output_format=ImageFormat.PNG,
        ),
        job_config=ImgGenJobConfig(is_sync_mode=False),
        job_report=ImgGenJobReport(
            img_gen_tokens_usage=ImgGenTokensUsage(
                job_metadata=job_metadata,
                inference_model_name="img-model",
                inference_model_id="img-model-id",
                unit_costs={CostCategory.INPUT: 1000, CostCategory.OUTPUT: 2000},
                nb_tokens_by_category={TokenCategory.INPUT: 100, TokenCategory.OUTPUT: 200},
            )
        ),
        job_metadata=job_metadata,
    )


def _make_extract_job(run_id: str) -> ExtractJob:
    job_metadata = _job_metadata(run_id)
    return ExtractJob(
        extract_input=ExtractInput(document_uri="/tmp/test.pdf"),  # ruff: ignore[hardcoded-temp-file]
        job_params=ExtractJobParams.make_default_extract_job_params(),
        job_config=ExtractJobConfig(),
        job_report=ExtractJobReport(
            extract_tokens_usage=ExtractTokensUsage(
                job_metadata=job_metadata,
                inference_model_name="extract-model",
                inference_model_id="extract-model-id",
                unit_costs={CostCategory.INPUT: 1000, CostCategory.OUTPUT: 1000},
                nb_tokens_by_category={TokenCategory.INPUT: 300, TokenCategory.OUTPUT: 400},
            )
        ),
        job_metadata=job_metadata,
    )


def _enable_ndjson_tracing(mocker: MockerFixture, traces_dir: Path) -> None:
    """Turn tracing on with an NDJSON backend in ``traces_dir``, so the runner fallback has somewhere to write."""
    cfg = get_config().runtime.tracing
    mocker.patch.object(cfg, "is_enabled", True)
    mocker.patch.object(cfg, "backend", TracingBackend.NDJSON)
    mocker.patch.object(cfg, "ndjson", NdjsonTracingConfig(traces_dir=str(traces_dir)))


def _usage_events(event_log: InMemoryEventLog, run_id: str) -> list[UsageReportEvent]:
    return [evt for evt in event_log.read_events(run_id) if isinstance(evt, UsageReportEvent)]


def _fallback_usage_events(traces_dir: Path, run_id: str) -> list[UsageReportEvent]:
    return [evt for evt in NdjsonEventLog(traces_dir=str(traces_dir)).read_events(run_id) if isinstance(evt, UsageReportEvent)]


def _register_spy_context(manager: ReportingManager, mocker: MockerFixture, *, run_id: str) -> Any:
    """Register a spy event log for the run's lookup key, as ``pipeline_run_setup`` or a workflow would."""
    event_log_spy = mocker.MagicMock()
    event_log_spy.writer_id = "registered_writer"
    event_log_spy.next_sequence.return_value = 0
    manager.set_event_log(context_key=_trace_context(run_id).lookup_key, event_log=event_log_spy, pipeline_run_id=run_id)
    return event_log_spy


@pytest.fixture(autouse=True)
def _reset_activity_event_log_state() -> Any:  # pyright: ignore[reportUnusedFunction]
    """Class-level state on ActivityEventLogCache persists across tests; reset it."""
    ActivityEventLogCache.reset_for_tests()
    yield
    ActivityEventLogCache.reset_for_tests()


class TestEmitUsageScopedEventLog:
    @pytest.mark.parametrize("is_isolated", [False, True])
    def test_scoped_event_log_takes_the_usage_event_and_nothing_else_does(self, tmp_path: Path, mocker: MockerFixture, is_isolated: bool) -> None:
        """Under a scoped log, the event lands in it alone: the registered context and the fallback get nothing."""
        _enable_ndjson_tracing(mocker, tmp_path)
        mocker.patch(_ISOLATION_PROBE_TARGET, return_value=is_isolated)
        manager = ReportingManager()
        manager.setup()
        registered_spy = _register_spy_context(manager, mocker, run_id="run_scoped")
        scoped_log = InMemoryEventLog(writer_id="leaf_capture")

        with scoped_event_log(scoped_log):
            manager.report_inference_job(_make_llm_job("run_scoped"))

        captured = _usage_events(scoped_log, "run_scoped")
        assert len(captured) == 1
        event = captured[0]
        assert event.pipeline_run_id == "run_scoped"
        assert event.writer_id == "leaf_capture"
        assert event.sequence == 0
        assert event.workflow_id == "wf_run_scoped--branch"
        assert event.attempt == 2
        assert event.lineage == [ExecutionAttempt(execution="wf_run_scoped", attempt=1)]
        assert event.path == "method.main/step_2"
        assert event.node_id == "run_scoped:node_3"
        assert event.mode.is_live
        assert event.tokens_usage.nb_tokens_by_category == {TokenCategory.INPUT: 100, TokenCategory.OUTPUT: 50}
        registered_spy.emit.assert_not_called()
        assert list(tmp_path.glob("**/*.ndjson")) == []

    @pytest.mark.parametrize(
        ("make_job", "model_name"),
        [
            (_make_llm_job, "llm-model"),
            (_make_img_gen_job, "img-model"),
            (_make_extract_job, "extract-model"),
        ],
    )
    def test_leaf_in_an_isolated_execution_captures_its_usage(
        self, tmp_path: Path, mocker: MockerFixture, make_job: Callable[[str], InferenceJobAbstract], model_name: str
    ) -> None:
        """The plugin's case: code running a leaf in an activity scopes a fresh log and reads the leaf's usage back."""
        _enable_ndjson_tracing(mocker, tmp_path)
        mocker.patch(_ISOLATION_PROBE_TARGET, return_value=True)
        fallback_spy = mocker.spy(ActivityEventLogCache, "get_or_create")
        manager = ReportingManager()
        manager.setup()

        leaf_log = InMemoryEventLog(writer_id="activity_leaf")
        with scoped_event_log(leaf_log):
            manager.report_inference_job(make_job("run_activity"))

        captured = _usage_events(leaf_log, "run_activity")
        assert [event.tokens_usage.inference_model_name for event in captured] == [model_name]
        fallback_spy.assert_not_called()
        assert _fallback_usage_events(tmp_path, "run_activity") == []

    def test_scoped_event_log_is_honoured_with_tracing_disabled(self, mocker: MockerFixture) -> None:
        """A set override implies tracing-enabled, for usage as for the tracer and the assembly."""
        mocker.patch.object(get_config().runtime.tracing, "is_enabled", False)
        mocker.patch(_ISOLATION_PROBE_TARGET, return_value=True)
        manager = ReportingManager()
        manager.setup()
        scoped_log = InMemoryEventLog()

        with scoped_event_log(scoped_log):
            manager.report_inference_job(_make_llm_job("run_tracing_off"))

        assert len(_usage_events(scoped_log, "run_tracing_off")) == 1

    def test_scoped_event_log_still_honours_the_costs_off_gate(self, mocker: MockerFixture) -> None:
        """A trace context with usage events off emits nothing, into the scoped log as anywhere else."""
        mocker.patch(_ISOLATION_PROBE_TARGET, return_value=True)
        manager = ReportingManager()
        manager.setup()
        scoped_log = InMemoryEventLog()

        with scoped_event_log(scoped_log):
            manager.report_inference_job(_make_llm_job("run_costs_off", emit_usage_events=False))

        assert scoped_log.read_events("run_costs_off") == []

    def test_scoped_event_log_emit_failure_is_best_effort(self, mocker: MockerFixture, caplog: pytest.LogCaptureFixture) -> None:
        """A scoped log whose emit fails with an infra error drops the event with a warning, as every path does."""
        manager = ReportingManager()
        manager.setup()
        failing_log = InMemoryEventLog()
        emit_spy = mocker.patch.object(failing_log, "emit", side_effect=OSError("disk full"))

        with caplog.at_level(logging.WARNING), scoped_event_log(failing_log):
            # Must not raise: the failure is logged and dropped.
            manager.report_inference_job(_make_llm_job("run_failing"))

        emit_spy.assert_called_once()
        assert any(record.levelno == logging.WARNING for record in caplog.records)

    def test_no_override_outside_isolation_takes_the_registered_context(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """With no scoped log, a registered context takes the event as before, and the fallback gets nothing."""
        _enable_ndjson_tracing(mocker, tmp_path)
        mocker.patch(_ISOLATION_PROBE_TARGET, return_value=False)
        manager = ReportingManager()
        manager.setup()
        registered_spy = _register_spy_context(manager, mocker, run_id="run_registered")

        assert get_event_log_override() is None
        manager.report_inference_job(_make_llm_job("run_registered"))

        registered_spy.emit.assert_called_once()
        emitted_event = registered_spy.emit.call_args.args[0]
        assert isinstance(emitted_event, UsageReportEvent)
        assert emitted_event.pipeline_run_id == "run_registered"
        assert emitted_event.writer_id == "registered_writer"
        assert emitted_event.workflow_id == "wf_run_registered--branch"
        assert emitted_event.path == "method.main/step_2"
        assert list(tmp_path.glob("**/*.ndjson")) == []

    def test_no_override_inside_isolation_takes_the_runner_fallback(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """With no scoped log, an isolated sub-execution skips the registered context for the fallback, as before."""
        _enable_ndjson_tracing(mocker, tmp_path)
        mocker.patch(_ISOLATION_PROBE_TARGET, return_value=True)
        manager = ReportingManager()
        manager.setup()
        registered_spy = _register_spy_context(manager, mocker, run_id="run_fallback")

        assert get_event_log_override() is None
        manager.report_inference_job(_make_llm_job("run_fallback"))

        registered_spy.emit.assert_not_called()
        fallback_events = _fallback_usage_events(tmp_path, "run_fallback")
        assert len(fallback_events) == 1
        assert fallback_events[0].writer_id.startswith("act_")
        assert fallback_events[0].workflow_id == "wf_run_fallback--branch"

    def test_leaving_the_scope_restores_the_previous_routing(self, mocker: MockerFixture) -> None:
        """Once the scope exits, the next event goes to the registered context again, and the scoped log keeps only its own."""
        mocker.patch(_ISOLATION_PROBE_TARGET, return_value=False)
        manager = ReportingManager()
        manager.setup()
        registered_spy = _register_spy_context(manager, mocker, run_id="run_restore")
        scoped_log = InMemoryEventLog()

        with scoped_event_log(scoped_log):
            manager.report_inference_job(_make_llm_job("run_restore"))
        manager.report_inference_job(_make_llm_job("run_restore"))

        assert len(_usage_events(scoped_log, "run_restore")) == 1
        registered_spy.emit.assert_called_once()

    @pytest.mark.asyncio
    async def test_concurrent_scopes_capture_only_their_own_usage(self, mocker: MockerFixture) -> None:
        """Two leaves running concurrently in one process, each in its own scope, never see each other's usage."""
        mocker.patch(_ISOLATION_PROBE_TARGET, return_value=True)
        manager = ReportingManager()
        manager.setup()

        async def run_leaf(run_id: str) -> InMemoryEventLog:
            leaf_log = InMemoryEventLog(writer_id=f"leaf_{run_id}")
            with scoped_event_log(leaf_log):
                # Yield so the two leaves interleave inside their scopes before either reports.
                await asyncio.sleep(0)
                manager.report_inference_job(_make_llm_job(run_id))
                await asyncio.sleep(0)
            return leaf_log

        first_log, second_log = await asyncio.gather(run_leaf("run_first"), run_leaf("run_second"))

        assert [event.pipeline_run_id for event in first_log.read_events("run_first")] == ["run_first"]
        assert first_log.read_events("run_second") == []
        assert [event.pipeline_run_id for event in second_log.read_events("run_second")] == ["run_second"]
        assert second_log.read_events("run_first") == []
