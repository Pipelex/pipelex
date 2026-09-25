"""The LLM worker holds its generation span as the Pipelex span active from its start to its end.

The span is started with the pipe's span as its explicit parent, read off the job metadata, and that
stays as it was; what changes is that the provider call runs with the span held, so a log line during
the call is joined to it, and the previous one comes back when the span ends, whichever way it ends.
OpenTelemetry's current span is never touched: inside the call it is whatever it was outside, the host's
or none, so a provider SDK's own instrumentation is never re-parented under the LLM span. Driven through
the public ``gen_text`` and ``gen_object`` on a worker whose provider half records the spans it runs under.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import INVALID_SPAN_ID, StatusCode
from pydantic import BaseModel
from typing_extensions import override

from pipelex.cogt.exceptions import LLMCompletionError
from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.cogt.llm.llm_job_components import LLMJobConfig, LLMJobParams
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.cogt.llm.llm_worker_abstract import LLMWorkerAbstract
from pipelex.cogt.llm.thinking_mode import ThinkingMode
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.cogt.usage.cost_category import CostCategory
from pipelex.system.job_metadata import JobMetadata, OtelContext, RunMetadata
from pipelex.system.telemetry.current_span import span_context_for_logs
from pipelex.system.telemetry.telemetry_manager_abstract import TelemetryManagerAbstract

if TYPE_CHECKING:
    from opentelemetry.sdk.trace import ReadableSpan
    from pytest_mock import MockerFixture

    from pipelex.tools.typing.pydantic_utils import BaseModelTypeVar

RUN_TRACE_ID = 0x0123456789ABCDEF0123456789ABCDEF
PIPE_SPAN_ID = 0x00000000000000AB


class _Answer(BaseModel):
    text: str


class _RecordingLLMWorker(LLMWorkerAbstract):
    """A worker whose provider half records the span a log line is joined to and OpenTelemetry's current span, and fails when asked to."""

    def __init__(self, *, inference_model: InferenceModelSpec, fails: bool) -> None:
        LLMWorkerAbstract.__init__(self, inference_model=inference_model, reporting_delegate=None)
        self.fails = fails
        self.seen_log_span_ids: list[int] = []
        self.seen_current_spans: list[object] = []

    def _record(self) -> None:
        log_span_context = span_context_for_logs()
        self.seen_log_span_ids.append(INVALID_SPAN_ID if log_span_context is None else log_span_context.span_id)
        self.seen_current_spans.append(trace.get_current_span())
        if self.fails:
            msg = "provider refused"
            raise LLMCompletionError(message=msg)

    @override
    async def _gen_text(self, llm_job: LLMJob) -> str:
        self._record()
        return "answer"

    @override
    async def _gen_object(self, llm_job: LLMJob, *, schema: type[BaseModelTypeVar]) -> BaseModelTypeVar:
        self._record()
        return schema.model_validate({"text": "answer"})


def _make_worker(*, fails: bool = False) -> _RecordingLLMWorker:
    inference_model = InferenceModelSpec(
        backend_name="openai",
        name="gpt-test",
        sdk="openai",
        model_type=ModelType.LLM,
        model_id="gpt-test-id",
        inputs=["text"],
        outputs=["text", "structured"],
        costs={CostCategory.INPUT: 1, CostCategory.OUTPUT: 2},
        thinking_mode=ThinkingMode.NONE,
        max_tokens=None,
        max_prompt_images=None,
    )
    return _RecordingLLMWorker(inference_model=inference_model, fails=fails)


def _make_llm_job() -> LLMJob:
    """A job run under a pipe whose span the metadata names as the parent."""
    job_metadata = JobMetadata(
        run_metadata=RunMetadata(user_id="pytest", pipeline_run_id="plr-llm", storage_scope="test/scope"),
        pipe_code="some_pipe",
        otel_context=OtelContext(trace_id=RUN_TRACE_ID, trace_name="some_pipe", trace_name_redacted="some_pipe", span_id=PIPE_SPAN_ID),
    )
    return LLMJob(
        job_metadata=job_metadata,
        llm_prompt=LLMPrompt(user_text="hello"),
        job_params=LLMJobParams(temperature=0.5),
        job_config=LLMJobConfig(schema_reask_max_attempts=1),
    )


def _only_span(exporter: InMemorySpanExporter) -> ReadableSpan:
    (span,) = exporter.get_finished_spans()
    return span


def _span_id(span: ReadableSpan) -> int:
    span_context = span.get_span_context()
    assert span_context is not None
    return int(span_context.span_id)


@pytest.fixture
def span_exporter(mocker: MockerFixture) -> InMemorySpanExporter:
    """The runtime's tracer, replaced by one exporting to memory, so the test reads back the span the worker started."""
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    mocker.patch.object(TelemetryManagerAbstract, "get_instance_tracer", return_value=provider.get_tracer(__name__))
    return exporter


@pytest.mark.asyncio
class TestLLMWorkerCurrentSpan:
    async def test_gen_text_runs_the_provider_call_under_its_span(self, span_exporter: InMemorySpanExporter) -> None:
        worker = _make_worker()

        assert await worker.gen_text(llm_job=_make_llm_job()) == "answer"

        llm_span = _only_span(span_exporter)
        assert worker.seen_log_span_ids == [_span_id(llm_span)]
        assert llm_span.parent is not None
        assert llm_span.parent.span_id == PIPE_SPAN_ID
        assert span_context_for_logs() is None

    async def test_gen_object_runs_the_provider_call_under_its_span(self, span_exporter: InMemorySpanExporter) -> None:
        worker = _make_worker()

        assert await worker.gen_object(llm_job=_make_llm_job(), schema=_Answer) == _Answer(text="answer")

        llm_span = _only_span(span_exporter)
        assert worker.seen_log_span_ids == [_span_id(llm_span)]
        assert span_context_for_logs() is None

    async def test_the_call_never_makes_its_span_opentelemetrys_current_one(self, span_exporter: InMemorySpanExporter) -> None:
        """Inside the call the current span is whatever it was outside, so the provider SDK's instrumentation is never re-parented."""
        host_tracer = TracerProvider().get_tracer(__name__)
        without_host = _make_worker()
        under_host = _make_worker()

        await without_host.gen_text(llm_job=_make_llm_job())
        with host_tracer.start_as_current_span("host") as host_span:
            await under_host.gen_object(llm_job=_make_llm_job(), schema=_Answer)

        assert without_host.seen_current_spans == [trace.INVALID_SPAN]
        assert under_host.seen_current_spans == [host_span]
        # A line logged in the call still names the LLM span, not the host's.
        assert under_host.seen_log_span_ids == [_span_id(span_exporter.get_finished_spans()[-1])]

    async def test_a_failed_call_restores_the_previous_span_and_is_recorded_once(self, span_exporter: InMemorySpanExporter) -> None:
        worker = _make_worker(fails=True)

        with pytest.raises(LLMCompletionError, match="provider refused"):
            await worker.gen_text(llm_job=_make_llm_job())

        llm_span = _only_span(span_exporter)
        assert worker.seen_log_span_ids == [_span_id(llm_span)]
        assert span_context_for_logs() is None
        # The worker's own error path records the failure; holding the span records nothing more.
        assert llm_span.status.status_code is StatusCode.ERROR
        assert [event.name for event in llm_span.events] == ["exception"]
