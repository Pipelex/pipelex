from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from openai import AsyncOpenAI
from openai.types import CompletionUsage
from openai.types.chat import ChatCompletion, ChatCompletionMessage
from openai.types.chat.chat_completion import Choice
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode

from pipelex.cogt.exceptions import LLMCompletionError, LLMCompletionRefusedError, LLMCompletionTruncatedError
from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.cogt.llm.llm_job_components import LLMJobConfig, LLMJobParams
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.cogt.llm.thinking_mode import ThinkingMode
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.cogt.usage.cost_category import CostCategory
from pipelex.cogt.usage.token_category import TokenCategory
from pipelex.providers.openai.openai_completions_factory import OpenAICompletionsFactory
from pipelex.providers.openai.openai_completions_llm_worker import OpenAICompletionsLLMWorker
from pipelex.reporting.reporting_protocol import ReportingProtocol
from pipelex.system.job_metadata import JobMetadata, OtelContext, RunMetadata
from pipelex.system.telemetry.otel_constants import GenAISpanAttr
from pipelex.system.telemetry.telemetry_manager_abstract import TelemetryManagerAbstract
from tests.helpers.completion_stop import STOP_TEST_PARTIAL_TEXT, STOP_TEST_PIPE_CODE

if TYPE_CHECKING:
    from typing import Literal
    from unittest.mock import MagicMock

    from opentelemetry.sdk.trace import ReadableSpan
    from pytest_mock import MockerFixture

INPUT_TOKENS = 50
OUTPUT_TOKENS = 256


def _completion(*, finish_reason: Literal["stop", "length", "content_filter"]) -> ChatCompletion:
    return ChatCompletion(
        id="chatcmpl_test",
        object="chat.completion",
        created=0,
        model="gpt-test-id",
        choices=[Choice(index=0, finish_reason=finish_reason, message=ChatCompletionMessage(role="assistant", content=STOP_TEST_PARTIAL_TEXT))],
        usage=CompletionUsage(prompt_tokens=INPUT_TOKENS, completion_tokens=OUTPUT_TOKENS, total_tokens=INPUT_TOKENS + OUTPUT_TOKENS),
    )


def _make_worker(mocker: MockerFixture, *, response: ChatCompletion) -> tuple[OpenAICompletionsLLMWorker, MagicMock]:
    """The worker built as its factory builds it, its SDK call answering with the response, its delegate recording."""
    sdk_client = AsyncOpenAI(api_key="test-key")
    mocker.patch.object(sdk_client.chat.completions, "create", new=mocker.AsyncMock(return_value=response))
    reporting_delegate = mocker.MagicMock(spec=ReportingProtocol)
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
    worker = OpenAICompletionsLLMWorker(
        openai_completions_factory=OpenAICompletionsFactory(is_http_url_enabled=False),
        sdk_instance=sdk_client,
        inference_model=inference_model,
        reporting_delegate=reporting_delegate,
    )
    return worker, reporting_delegate


def _make_llm_job() -> LLMJob:
    """A text job run under a pipe whose span the metadata names as the parent, so the call starts a span."""
    job_metadata = JobMetadata(
        run_metadata=RunMetadata(user_id="pytest", pipeline_run_id="plr-stop", storage_scope="test/scope", read_scope=None),
        pipe_code=STOP_TEST_PIPE_CODE,
        otel_context=OtelContext(
            trace_id=0x0123456789ABCDEF0123456789ABCDEF,
            trace_name=STOP_TEST_PIPE_CODE,
            trace_name_redacted=STOP_TEST_PIPE_CODE,
            span_id=0x00000000000000AB,
        ),
    )
    return LLMJob(
        job_metadata=job_metadata,
        llm_prompt=LLMPrompt(user_text="Summarize the contract."),
        job_params=LLMJobParams(temperature=0.5, max_tokens=OUTPUT_TOKENS),
        job_config=LLMJobConfig(schema_reask_max_attempts=1),
    )


def _only_span(exporter: InMemorySpanExporter) -> ReadableSpan:
    (span,) = exporter.get_finished_spans()
    return span


def _assert_reported_once_with_its_usage(*, reporting_delegate: MagicMock, llm_job: LLMJob) -> None:
    reporting_delegate.report_inference_job.assert_called_once_with(inference_job=llm_job)
    tokens_usage = llm_job.job_report.llm_tokens_usage
    assert tokens_usage is not None
    assert tokens_usage.nb_tokens_by_category[TokenCategory.INPUT] == INPUT_TOKENS
    assert tokens_usage.nb_tokens_by_category[TokenCategory.OUTPUT] == OUTPUT_TOKENS
    assert llm_job.job_metadata.completed_at is not None


@pytest.fixture
def span_exporter(mocker: MockerFixture) -> InMemorySpanExporter:
    """The runtime's tracer, replaced by one exporting to memory, so the test reads back the span the worker started."""
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    mocker.patch.object(TelemetryManagerAbstract, "get_instance_tracer", return_value=provider.get_tracer(__name__))
    return exporter


@pytest.mark.asyncio(loop_scope="class")
class TestLLMWorkerStoppedTextUsage:
    @pytest.mark.parametrize(
        ("finish_reason", "expected_error"),
        [
            ("length", LLMCompletionTruncatedError),
            ("content_filter", LLMCompletionRefusedError),
        ],
    )
    async def test_a_stopped_text_raises_and_reports_its_billed_usage(
        self,
        mocker: MockerFixture,
        span_exporter: InMemorySpanExporter,
        finish_reason: Literal["length", "content_filter"],
        expected_error: type[LLMCompletionError],
    ) -> None:
        """The provider answered and billed the text the stop check refused: its usage is reported once and put on the span."""
        worker, reporting_delegate = _make_worker(mocker, response=_completion(finish_reason=finish_reason))
        llm_job = _make_llm_job()

        with pytest.raises(expected_error):
            await worker.gen_text(llm_job=llm_job)

        _assert_reported_once_with_its_usage(reporting_delegate=reporting_delegate, llm_job=llm_job)
        llm_span = _only_span(span_exporter)
        assert llm_span.status.status_code == StatusCode.ERROR
        assert llm_span.attributes is not None
        assert llm_span.attributes[GenAISpanAttr.USAGE_INPUT_TOKENS] == INPUT_TOKENS
        assert llm_span.attributes[GenAISpanAttr.USAGE_OUTPUT_TOKENS] == OUTPUT_TOKENS

    async def test_a_returned_text_is_reported_once(self, mocker: MockerFixture, span_exporter: InMemorySpanExporter) -> None:
        worker, reporting_delegate = _make_worker(mocker, response=_completion(finish_reason="stop"))
        llm_job = _make_llm_job()

        assert await worker.gen_text(llm_job=llm_job) == STOP_TEST_PARTIAL_TEXT

        _assert_reported_once_with_its_usage(reporting_delegate=reporting_delegate, llm_job=llm_job)
        llm_span = _only_span(span_exporter)
        assert llm_span.status.status_code == StatusCode.OK
        assert llm_span.attributes is not None
        assert llm_span.attributes[GenAISpanAttr.USAGE_OUTPUT_TOKENS] == OUTPUT_TOKENS

    async def test_a_failure_with_no_usage_recorded_reports_nothing(self, mocker: MockerFixture, span_exporter: InMemorySpanExporter) -> None:
        """A provider answer with no usage leaves nothing to report, even when its stop check refuses the text."""
        response = _completion(finish_reason="length")
        response.usage = None
        worker, reporting_delegate = _make_worker(mocker, response=response)

        with pytest.raises(LLMCompletionTruncatedError):
            await worker.gen_text(llm_job=_make_llm_job())

        reporting_delegate.report_inference_job.assert_not_called()
        assert _only_span(span_exporter).status.status_code == StatusCode.ERROR
