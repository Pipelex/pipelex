"""Runner-side fallback emission for NON-LLM inference jobs (img-gen / extract).

``ReportingManager.report_inference_job`` dispatches by job type, and the
img-gen / extract branches (``_report_img_gen_job`` / ``_report_extract_job``)
are exercised by no test in any mode — every usage test drives an ``LLMJob``.
This pins that a non-LLM job with no registered event-log context (the runner
process) emits its ``UsageReportEvent`` through the per-process fallback, that
the ``AnyTokensUsage`` discriminated union restores the right concrete type on
read-back, and that it prices into the run total.
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from pipelex.cogt.extract.extract_input import ExtractInput
from pipelex.cogt.extract.extract_job import ExtractJob
from pipelex.cogt.extract.extract_job_components import ExtractJobConfig, ExtractJobParams, ExtractJobReport
from pipelex.cogt.extract.extract_report import ExtractTokensUsage
from pipelex.cogt.img_gen.img_gen_job import ImgGenJob
from pipelex.cogt.img_gen.img_gen_job_components import (
    AspectRatio,
    Background,
    ImgGenJobConfig,
    ImgGenJobParams,
    ImgGenJobReport,
)
from pipelex.cogt.img_gen.img_gen_prompt import ImgGenPrompt
from pipelex.cogt.img_gen.img_gen_report import ImgGenTokensUsage
from pipelex.cogt.usage.cost_category import CostCategory
from pipelex.cogt.usage.cost_registry import CostRegistry
from pipelex.cogt.usage.token_category import TokenCategory
from pipelex.config import get_config
from pipelex.reporting.reporting_manager import ReportingManager
from pipelex.system.configuration.configs import NdjsonTracingConfig, TracingBackend
from pipelex.system.data_inclusion_config import DataInclusionConfig
from pipelex.system.job_metadata import JobMetadata
from pipelex.system.trace_context import TraceContext
from pipelex.tools.misc.image_utils import ImageFormat
from pipelex.tracing.activity_event_log import ActivityEventLogCache
from pipelex.tracing.ndjson_event_log import NdjsonEventLog
from pipelex.tracing.trace_events import UsageReportEvent
from pipelex.tracing.usage_aggregator import UsageAggregator

_DATA_INCLUSION_OFF = DataInclusionConfig(
    pipe_and_concept_registry=False,
    stuff_json_content=False,
    stuff_text_content=False,
    stuff_html_content=False,
    error_stack_traces=False,
)


@pytest.fixture(autouse=True)
def _reset_activity_event_log_state() -> object:  # pyright: ignore[reportUnusedFunction]
    ActivityEventLogCache.reset_for_tests()
    yield
    ActivityEventLogCache.reset_for_tests()


def _enable_ndjson_tracing(mocker: MockerFixture, traces_dir: Path) -> None:
    cfg = get_config().runtime.tracing
    mocker.patch.object(cfg, "is_enabled", True)
    mocker.patch.object(cfg, "backend", TracingBackend.NDJSON)
    mocker.patch.object(cfg, "ndjson", NdjsonTracingConfig(traces_dir=str(traces_dir)))


def _trace_context(run_id: str, tracer_key: str) -> TraceContext:
    return TraceContext(
        graph_id=run_id,
        tracer_key=tracer_key,
        parent_node_id="g:node_0",
        node_sequence=0,
        data_inclusion=_DATA_INCLUSION_OFF,
    )


def _job_metadata(run_id: str, tracer_key: str) -> JobMetadata:
    now = datetime.now(UTC)
    return JobMetadata(
        user_id="test-user",
        pipeline_run_id=run_id,
        trace_context=_trace_context(run_id, tracer_key),
        started_at=now,
        completed_at=now + timedelta(seconds=1),
    )


def _make_img_gen_job(run_id: str) -> ImgGenJob:
    job_metadata = _job_metadata(run_id, "wf_img")
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
    job_metadata = _job_metadata(run_id, "wf_extract")
    return ExtractJob(
        extract_input=ExtractInput(document_uri="/tmp/test.pdf"),  # noqa: S108
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


class TestEmitRunnerFallbackNonLLM:
    """The runner fallback emits img-gen and extract usage, not just LLM usage."""

    def test_img_gen_usage_emitted_via_runner_fallback(self, tmp_path: Path, mocker: MockerFixture) -> None:
        _enable_ndjson_tracing(mocker, tmp_path)
        manager = ReportingManager()
        manager.setup()

        manager.report_inference_job(_make_img_gen_job("run_img"))

        reader = NdjsonEventLog(traces_dir=str(tmp_path))
        events = reader.read_events("run_img")
        usage_events = [evt for evt in events if isinstance(evt, UsageReportEvent)]
        assert len(usage_events) == 1
        assert usage_events[0].writer_id.startswith("act_")
        assert isinstance(usage_events[0].tokens_usage, ImgGenTokensUsage)

        aggregated = CostRegistry.aggregate_costs(tokens_usages=UsageAggregator.aggregate(events))
        assert aggregated.total_nb_tokens == 300  # 100 input + 200 output
        assert aggregated.model_types == {"img-model": "img_gen"}
        assert aggregated.has_reportable_usage is True

    def test_extract_usage_emitted_via_runner_fallback(self, tmp_path: Path, mocker: MockerFixture) -> None:
        _enable_ndjson_tracing(mocker, tmp_path)
        manager = ReportingManager()
        manager.setup()

        manager.report_inference_job(_make_extract_job("run_extract"))

        reader = NdjsonEventLog(traces_dir=str(tmp_path))
        events = reader.read_events("run_extract")
        usage_events = [evt for evt in events if isinstance(evt, UsageReportEvent)]
        assert len(usage_events) == 1
        assert usage_events[0].writer_id.startswith("act_")
        assert isinstance(usage_events[0].tokens_usage, ExtractTokensUsage)

        aggregated = CostRegistry.aggregate_costs(tokens_usages=UsageAggregator.aggregate(events))
        assert aggregated.total_nb_tokens == 700  # 300 input + 400 output
        assert aggregated.model_types == {"extract-model": "extract"}
        assert aggregated.has_reportable_usage is True
