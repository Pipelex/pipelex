"""With ``join_host_trace`` on, the LLM worker makes its generation span current for the provider call.

The span still takes its parent from the job metadata; what changes is that the provider call runs with the
span as OpenTelemetry's current span, so a provider SDK's own instrumentation, a span of the host's here,
nests under it, and the previous current span comes back when the call ends, whichever way it ends. The
sampled flag the metadata carries is followed, so a call in a run the host sampled out records nothing.
With the switch off, ``test_llm_worker_current_span`` pins that the current span is left alone.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
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
from pipelex.system.telemetry.otel_factory import OtelFactory
from pipelex.system.telemetry.telemetry_manager_abstract import TelemetryManagerAbstract

if TYPE_CHECKING:
    from opentelemetry.sdk.trace import ReadableSpan
    from opentelemetry.trace import Tracer
    from pytest_mock import MockerFixture

    from pipelex.tools.typing.pydantic_utils import BaseModelTypeVar

RUN_TRACE_ID = 0x0123456789ABCDEF0123456789ABCDEF
PIPE_SPAN_ID = 0x00000000000000AB


class _Answer(BaseModel):
    text: str


class _HostInstrumentedLLMWorker(LLMWorkerAbstract):
    """A worker whose provider half records OpenTelemetry's current span and opens a span of the host's, as a provider SDK would."""

    def __init__(self, *, inference_model: InferenceModelSpec, host_tracer: Tracer, fails: bool) -> None:
        LLMWorkerAbstract.__init__(self, inference_model=inference_model, reporting_delegate=None)
        self.host_tracer = host_tracer
        self.fails = fails
        self.seen_current_span_ids: list[int] = []

    def _record(self) -> None:
        self.seen_current_span_ids.append(trace.get_current_span().get_span_context().span_id)
        with self.host_tracer.start_as_current_span("provider http call"):
            pass
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


def _make_worker(*, host_tracer: Tracer, fails: bool = False) -> _HostInstrumentedLLMWorker:
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
    return _HostInstrumentedLLMWorker(inference_model=inference_model, host_tracer=host_tracer, fails=fails)


def _make_llm_job(*, is_sampled: bool = True) -> LLMJob:
    """A job run under a pipe whose span, and whose sampled flag, the metadata carries."""
    job_metadata = JobMetadata(
        run_metadata=RunMetadata(user_id="pytest", pipeline_run_id="plr-llm", storage_scope="test/scope", read_scope=None),
        pipe_code="some_pipe",
        otel_context=OtelContext(
            trace_id=RUN_TRACE_ID, trace_name="some_pipe", trace_name_redacted="some_pipe", span_id=PIPE_SPAN_ID, is_sampled=is_sampled
        ),
    )
    return LLMJob(
        job_metadata=job_metadata,
        llm_prompt=LLMPrompt(user_text="hello"),
        job_params=LLMJobParams(temperature=0.5),
        job_config=LLMJobConfig(schema_reask_max_attempts=1),
    )


def _span_id(span: ReadableSpan) -> int:
    span_context = span.get_span_context()
    assert span_context is not None
    return int(span_context.span_id)


@pytest.mark.asyncio
class TestLLMWorkerJoinHostTrace:
    @pytest.fixture
    def pipelex_spans(self, mocker: MockerFixture) -> InMemorySpanExporter:
        """Pipelex's own tracer exporting to memory, and the switch on."""
        exporter = InMemorySpanExporter()
        provider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        mocker.patch.object(TelemetryManagerAbstract, "get_instance_tracer", return_value=provider.get_tracer("pipelex"))
        mocker.patch.object(TelemetryManagerAbstract, "is_join_host_trace_enabled", return_value=True)
        return exporter

    @pytest.fixture
    def host_spans(self) -> InMemorySpanExporter:
        return InMemorySpanExporter()

    @pytest.fixture
    def host_tracer(self, host_spans: InMemorySpanExporter) -> Tracer:
        provider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(host_spans))
        return provider.get_tracer("host")

    @pytest.mark.parametrize("is_structured", [False, True])
    async def test_the_provider_call_runs_with_the_llm_span_current(
        self,
        pipelex_spans: InMemorySpanExporter,
        host_spans: InMemorySpanExporter,
        host_tracer: Tracer,
        is_structured: bool,
    ) -> None:
        worker = _make_worker(host_tracer=host_tracer)

        with host_tracer.start_as_current_span("host request") as host_request:
            if is_structured:
                assert await worker.gen_object(llm_job=_make_llm_job(), schema=_Answer) == _Answer(text="answer")
            else:
                assert await worker.gen_text(llm_job=_make_llm_job()) == "answer"
            assert trace.get_current_span() is host_request

        (llm_span,) = pipelex_spans.get_finished_spans()
        assert llm_span.parent is not None
        assert llm_span.parent.span_id == PIPE_SPAN_ID
        assert worker.seen_current_span_ids == [_span_id(llm_span)]
        provider_span = next(span for span in host_spans.get_finished_spans() if span.name == "provider http call")
        assert provider_span.parent is not None
        assert provider_span.parent.span_id == _span_id(llm_span)

    async def test_a_failed_call_restores_the_previous_current_span(self, pipelex_spans: InMemorySpanExporter, host_tracer: Tracer) -> None:
        worker = _make_worker(host_tracer=host_tracer, fails=True)

        with pytest.raises(LLMCompletionError, match="provider refused"):
            await worker.gen_text(llm_job=_make_llm_job())

        (llm_span,) = pipelex_spans.get_finished_spans()
        assert worker.seen_current_span_ids == [_span_id(llm_span)]
        assert trace.get_current_span() is trace.INVALID_SPAN

    async def test_a_call_in_a_run_the_host_sampled_out_records_nothing(
        self, pipelex_spans: InMemorySpanExporter, host_spans: InMemorySpanExporter, host_tracer: Tracer
    ) -> None:
        worker = _make_worker(host_tracer=host_tracer)

        assert await worker.gen_text(llm_job=_make_llm_job(is_sampled=False)) == "answer"

        assert pipelex_spans.get_finished_spans() == ()
        # The host's own span opened under the unsampled LLM span is dropped by the host's parent-based sampler.
        assert host_spans.get_finished_spans() == ()

    @pytest.mark.parametrize("is_sampled", [True, False])
    async def test_a_span_that_records_nothing_serializes_no_content(
        self, mocker: MockerFixture, pipelex_spans: InMemorySpanExporter, host_tracer: Tracer, is_sampled: bool
    ) -> None:
        """The prompt and the completion object are serialized only for a span that records them."""
        stringify_json = mocker.patch.object(OtelFactory, "stringify_json", return_value="[]")
        worker = _make_worker(host_tracer=host_tracer)

        assert await worker.gen_object(llm_job=_make_llm_job(is_sampled=is_sampled), schema=_Answer) == _Answer(text="answer")

        # The prompt when the span starts, and the completion object when it ends.
        assert stringify_json.call_count == (2 if is_sampled else 0)
        assert len(pipelex_spans.get_finished_spans()) == (1 if is_sampled else 0)
