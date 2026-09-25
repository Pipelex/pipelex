"""The LLM worker makes its generation span current from its start to its end.

The span is started with the pipe's span as its explicit parent, read off the job metadata, and that
stays as it was; what changes is that the provider call runs with the span current, so a log line or a
provider SDK's own span during the call is joined to it, and the previous context comes back when the
span ends, whichever way it ends. Driven through the public ``gen_text`` and ``gen_object`` on a worker
whose provider half records the span it runs under.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode
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
    """A worker whose provider half records the span current while it runs, and fails when asked to."""

    def __init__(self, *, inference_model: InferenceModelSpec, fails: bool) -> None:
        LLMWorkerAbstract.__init__(self, inference_model=inference_model, reporting_delegate=None)
        self.fails = fails
        self.seen_span_ids: list[int] = []

    def _record(self) -> None:
        self.seen_span_ids.append(trace.get_current_span().get_span_context().span_id)
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
        assert worker.seen_span_ids == [_span_id(llm_span)]
        assert llm_span.parent is not None
        assert llm_span.parent.span_id == PIPE_SPAN_ID
        assert trace.get_current_span() is trace.INVALID_SPAN

    async def test_gen_object_runs_the_provider_call_under_its_span(self, span_exporter: InMemorySpanExporter) -> None:
        worker = _make_worker()

        assert await worker.gen_object(llm_job=_make_llm_job(), schema=_Answer) == _Answer(text="answer")

        llm_span = _only_span(span_exporter)
        assert worker.seen_span_ids == [_span_id(llm_span)]
        assert trace.get_current_span() is trace.INVALID_SPAN

    async def test_a_failed_call_restores_the_context_and_is_recorded_once(self, span_exporter: InMemorySpanExporter) -> None:
        worker = _make_worker(fails=True)

        with pytest.raises(LLMCompletionError, match="provider refused"):
            await worker.gen_text(llm_job=_make_llm_job())

        llm_span = _only_span(span_exporter)
        assert worker.seen_span_ids == [_span_id(llm_span)]
        assert trace.get_current_span() is trace.INVALID_SPAN
        # The worker's own error path records the failure; making the span current records nothing more.
        assert llm_span.status.status_code is StatusCode.ERROR
        assert [event.name for event in llm_span.events] == ["exception"]
