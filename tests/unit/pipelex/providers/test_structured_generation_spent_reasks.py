"""A structured generation whose re-asks run out still reports what every attempt spent, on its generation span.

``instructor`` re-asks the model when an answer fails the schema, and every request is billed. Its own totals cover
OpenAI- and Anthropic-shaped answers only, so each worker hands it the hooks of an ``InstructorAttempts`` recorder, which
counts the requests and sums the usage each answer reports. These tests drive each provider worker's public
``gen_object`` through a re-ask budget spent on billable invalid answers and read back the failed generation's span: its
error status, its tokens summed over the attempts, the cost of those tokens at the model's rates, and the attempt count.

The worker tests stand in for ``instructor`` with a mock that plays its loop: it calls the hooks it is handed once per
request, as ``instructor`` does, and raises what the real loop raises once the budget is spent. The last tests drive the
real loop, over a mocked HTTP transport, to pin that ``instructor`` calls the hooks once per request and hands each
answer to them before it folds that answer's usage into a running total.
"""

from __future__ import annotations

import json
import math
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import anthropic
import httpx
import openai
import pytest
from anthropic.types import Usage as AnthropicUsage
from google.genai import types as genai_types
from instructor import Mode, from_anthropic, from_openai
from instructor.core import InstructorRetryException
from mistralai.client.models import UsageInfo as MistralUsage
from openai.types.completion_usage import CompletionUsage
from openai.types.responses import ResponseUsage
from openai.types.responses.response_usage import InputTokensDetails, OutputTokensDetails
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode
from pydantic import ValidationError

from pipelex.cogt.exceptions import CogtError
from pipelex.cogt.llm.instructor_attempts import InstructorAttempts
from pipelex.cogt.llm.instructor_retry import make_instructor_schema_retrying
from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.cogt.llm.llm_job_components import LLMJobConfig, LLMJobParams
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.cogt.llm.thinking_mode import ThinkingMode
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.cogt.usage.cost_category import CostCategory
from pipelex.cogt.usage.token_category import NbTokensByCategoryDict, TokenCategory
from pipelex.providers.anthropic.anthropic_factory import AnthropicFactory
from pipelex.providers.anthropic.anthropic_llm_worker import AnthropicLLMWorker
from pipelex.providers.google.google_llm_worker import GoogleLLMWorker
from pipelex.providers.mistral.mistral_factory import MistralFactory
from pipelex.providers.mistral.mistral_llm_worker import MistralLLMWorker
from pipelex.providers.openai.openai_completions_factory import OpenAICompletionsFactory
from pipelex.providers.openai.openai_completions_llm_worker import OpenAICompletionsLLMWorker
from pipelex.providers.openai.openai_responses_factory import OpenAIResponsesFactory
from pipelex.providers.openai.openai_responses_llm_worker import OpenAIResponsesLLMWorker
from pipelex.reporting.reporting_protocol import ReportingProtocol
from pipelex.system.job_metadata import JobMetadata, OtelContext, RunMetadata
from pipelex.system.telemetry.otel_constants import GenAISpanAttr, PipelexSpanAttr
from pipelex.system.telemetry.telemetry_manager_abstract import TelemetryManagerAbstract
from tests.helpers.instructor_test_utils import DummySchema, wrap_in_instructor_retry

if TYPE_CHECKING:
    from collections.abc import Callable

    from pytest_mock import MockerFixture

    from pipelex.cogt.llm.llm_worker_abstract import LLMWorkerAbstract

_MAX_ATTEMPTS = 3
# What each billable invalid answer reports, and what the re-asks spent in all, priced at $1 per million tokens in and
# $2 out: 3,000 tokens in for $0.003 and 600 out for $0.0012.
_ANSWER_INPUT_TOKENS = 1000
_ANSWER_OUTPUT_TOKENS = 200
_RATES = {CostCategory.INPUT: 1.0, CostCategory.OUTPUT: 2.0}
_SPENT_INPUT_TOKENS = _MAX_ATTEMPTS * _ANSWER_INPUT_TOKENS
_SPENT_OUTPUT_TOKENS = _MAX_ATTEMPTS * _ANSWER_OUTPUT_TOKENS
_SPENT_INPUT_COST_USD = 0.003
_SPENT_OUTPUT_COST_USD = 0.0012
_SPENT_COST_USD = 0.0042
_RUN_OTEL_CONTEXT = OtelContext(
    trace_id=0x0123456789ABCDEF0123456789ABCDEF, trace_name="some_pipe", trace_name_redacted="some_pipe", span_id=0xAB, is_sampled=True
)


def _model(*, sdk: str, model_id: str) -> InferenceModelSpec:
    return InferenceModelSpec(
        backend_name="some_backend",
        name="some-handle",
        sdk=sdk,
        model_type=ModelType.LLM,
        model_id=model_id,
        inputs=["text"],
        outputs=["text", "structured"],
        costs=_RATES,
        thinking_mode=ThinkingMode.NONE,
        max_tokens=4096,
        max_prompt_images=None,
    )


def _object_job() -> LLMJob:
    """A structured generation under a run's span, re-asking up to the budget the tests spend."""
    return LLMJob(
        job_metadata=JobMetadata(
            run_metadata=RunMetadata(user_id="pytest", storage_scope="test/scope", read_scope=None, pipeline_run_id="plr-reasks"),
            pipe_code="some_pipe",
            otel_context=_RUN_OTEL_CONTEXT,
        ),
        llm_prompt=LLMPrompt(user_text="Generate a structured object."),
        job_params=LLMJobParams(temperature=0.5),
        job_config=LLMJobConfig(schema_reask_max_attempts=_MAX_ATTEMPTS),
    )


def _schema_failure() -> ValidationError:
    """The parse failure each invalid answer ends in."""
    try:
        DummySchema.model_validate({"wrong": 1})
    except ValidationError as validation_error:
        return validation_error
    msg = "the invalid answer validated"
    raise AssertionError(msg)


def _playing_instructors_loop(mocker: MockerFixture, *, answer: Any) -> Any:
    """A stand-in for `create_with_completion` that plays a re-ask budget spent on billable invalid answers.

    Each request calls the hooks the worker passed, the request's arguments then the answer, as `instructor` does, and
    the loop ends the way the real one ends once the budget is spent.
    """

    def create_with_completion(**kwargs: Any) -> Any:
        hooks = kwargs["hooks"]
        for _ in range(_MAX_ATTEMPTS):
            hooks.emit_completion_arguments(model=kwargs.get("model"))
            hooks.emit_completion_response(answer)
        schema_failure = _schema_failure()
        raise wrap_in_instructor_retry(schema_failure, earlier_parse_failures=[schema_failure] * (_MAX_ATTEMPTS - 1))  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]

    return mocker.AsyncMock(side_effect=create_with_completion)


def _openai_completions_worker(mocker: MockerFixture) -> LLMWorkerAbstract:
    worker = object.__new__(OpenAICompletionsLLMWorker)
    worker.reporting_delegate = None
    worker.inference_model = _model(sdk="openai", model_id="gpt-test-2026")
    factory = mocker.MagicMock()
    factory.make_simple_messages = mocker.AsyncMock(return_value=[])
    factory.make_extras = mocker.MagicMock(return_value=({}, {}))
    factory.make_nb_tokens_by_category = object.__new__(OpenAICompletionsFactory).make_nb_tokens_by_category
    worker.openai_completions_factory = factory
    instructor_client = mocker.MagicMock()
    answer = SimpleNamespace(
        usage=CompletionUsage(
            prompt_tokens=_ANSWER_INPUT_TOKENS, completion_tokens=_ANSWER_OUTPUT_TOKENS, total_tokens=_ANSWER_INPUT_TOKENS + _ANSWER_OUTPUT_TOKENS
        )
    )
    instructor_client.chat.completions.create_with_completion = _playing_instructors_loop(mocker, answer=answer)
    worker.instructor_for_objects = instructor_client
    return worker


def _openai_responses_worker(mocker: MockerFixture) -> LLMWorkerAbstract:
    worker = object.__new__(OpenAIResponsesLLMWorker)
    worker.reporting_delegate = None
    worker.inference_model = _model(sdk="openai_responses", model_id="gpt-test-2026")
    factory = mocker.MagicMock()
    factory.make_input_items = mocker.AsyncMock(return_value=[])
    factory.make_extras = mocker.MagicMock(return_value=({}, {}))
    factory.make_nb_tokens_by_category = object.__new__(OpenAIResponsesFactory).make_nb_tokens_by_category
    worker.openai_responses_factory = factory
    instructor_client = mocker.MagicMock()
    answer = SimpleNamespace(
        usage=ResponseUsage(
            input_tokens=_ANSWER_INPUT_TOKENS,
            output_tokens=_ANSWER_OUTPUT_TOKENS,
            total_tokens=_ANSWER_INPUT_TOKENS + _ANSWER_OUTPUT_TOKENS,
            input_tokens_details=InputTokensDetails(cached_tokens=0),
            output_tokens_details=OutputTokensDetails(reasoning_tokens=0),
        )
    )
    instructor_client.responses.create_with_completion = _playing_instructors_loop(mocker, answer=answer)
    worker.instructor_for_objects = instructor_client
    return worker


def _anthropic_worker(mocker: MockerFixture) -> LLMWorkerAbstract:
    config = mocker.MagicMock()
    config.inference.llm.anthropic.structured_output_timeout_seconds = 1200
    mocker.patch("pipelex.providers.anthropic.anthropic_llm_worker.get_config", return_value=config)
    mocker.patch("pipelex.providers.anthropic.anthropic_llm_worker.AnthropicFactory.make_simple_messages", new=mocker.AsyncMock(return_value=[]))
    mocker.patch("pipelex.providers.anthropic.anthropic_llm_worker.AnthropicFactory.calculate_safe_max_tokens_for_timeout", return_value=4096)
    worker = object.__new__(AnthropicLLMWorker)
    worker.reporting_delegate = None
    worker.inference_model = _model(sdk="anthropic", model_id="claude-test-2026")
    worker.extras_factory = None
    worker.extra_config = {}
    worker.default_max_tokens = 4096
    instructor_client = mocker.MagicMock()
    answer = SimpleNamespace(usage=AnthropicUsage(input_tokens=_ANSWER_INPUT_TOKENS, output_tokens=_ANSWER_OUTPUT_TOKENS))
    instructor_client.chat.completions.create_with_completion = _playing_instructors_loop(mocker, answer=answer)
    worker.instructor_for_objects = instructor_client
    return worker


def _mistral_worker(mocker: MockerFixture) -> LLMWorkerAbstract:
    worker = object.__new__(MistralLLMWorker)
    worker.reporting_delegate = None
    worker.inference_model = _model(sdk="mistral", model_id="mistral-test-2026")
    worker.default_max_tokens = 4096
    factory = mocker.MagicMock()
    factory.make_simple_messages_openai_typed = mocker.AsyncMock(return_value=[])
    factory.make_nb_tokens_by_category = object.__new__(MistralFactory).make_nb_tokens_by_category
    worker.mistral_factory = factory
    instructor_client = mocker.MagicMock()
    answer = SimpleNamespace(
        usage=MistralUsage(
            prompt_tokens=_ANSWER_INPUT_TOKENS, completion_tokens=_ANSWER_OUTPUT_TOKENS, total_tokens=_ANSWER_INPUT_TOKENS + _ANSWER_OUTPUT_TOKENS
        )
    )
    instructor_client.chat.completions.create_with_completion = _playing_instructors_loop(mocker, answer=answer)
    worker.instructor_for_objects = instructor_client
    return worker


def _google_worker(mocker: MockerFixture) -> LLMWorkerAbstract:
    mocker.patch("pipelex.providers.google.google_llm_worker.GoogleFactory.prepare_user_contents", new_callable=mocker.AsyncMock, return_value=[])
    worker = object.__new__(GoogleLLMWorker)
    worker.reporting_delegate = None
    worker.inference_model = _model(sdk="google", model_id="gemini-test-2026")
    instructor_client = mocker.MagicMock()
    answer = SimpleNamespace(
        usage_metadata=genai_types.GenerateContentResponseUsageMetadata(
            prompt_token_count=_ANSWER_INPUT_TOKENS, candidates_token_count=_ANSWER_OUTPUT_TOKENS
        )
    )
    instructor_client.chat.completions.create_with_completion = _playing_instructors_loop(mocker, answer=answer)
    worker.instructor_for_objects = instructor_client
    return worker


_WORKERS = [
    pytest.param(_openai_completions_worker, id="openai-completions"),
    pytest.param(_openai_responses_worker, id="openai-responses"),
    pytest.param(_anthropic_worker, id="anthropic"),
    pytest.param(_mistral_worker, id="mistral"),
    pytest.param(_google_worker, id="google"),
]


@pytest.fixture
def span_exporter(mocker: MockerFixture) -> InMemorySpanExporter:
    """The runtime's tracer, replaced by one exporting to memory, so the test reads back the span the worker started."""
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    mocker.patch.object(TelemetryManagerAbstract, "get_instance_tracer", return_value=provider.get_tracer(__name__))
    return exporter


def _assert_spent_reasks_on(span: ReadableSpan) -> None:
    """The failed generation's span holds what every attempt spent, priced, and how many attempts there were."""
    attributes = dict(span.attributes or {})
    assert span.status.status_code == StatusCode.ERROR
    assert attributes[GenAISpanAttr.ERROR_TYPE] == "content"
    assert attributes[PipelexSpanAttr.ATTEMPT_COUNT] == _MAX_ATTEMPTS
    assert (attributes[GenAISpanAttr.USAGE_INPUT_TOKENS], attributes[GenAISpanAttr.USAGE_OUTPUT_TOKENS]) == (
        _SPENT_INPUT_TOKENS,
        _SPENT_OUTPUT_TOKENS,
    )
    assert math.isclose(float(attributes[PipelexSpanAttr.INPUT_COST_USD]), _SPENT_INPUT_COST_USD)  # type: ignore[arg-type]
    assert math.isclose(float(attributes[PipelexSpanAttr.OUTPUT_COST_USD]), _SPENT_OUTPUT_COST_USD)  # type: ignore[arg-type]
    assert math.isclose(float(attributes[PipelexSpanAttr.TOTAL_COST_USD]), _SPENT_COST_USD)  # type: ignore[arg-type]


# A tool call whose arguments fail `DummySchema`, in each provider's shape, billed like every answer.
_OPENAI_INVALID_ANSWER: dict[str, Any] = {
    "id": "chatcmpl-invalid",
    "object": "chat.completion",
    "created": 0,
    "model": "gpt-test-2026",
    "choices": [
        {
            "index": 0,
            "finish_reason": "tool_calls",
            "message": {
                "role": "assistant",
                "content": None,
                "tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "DummySchema", "arguments": json.dumps({"wrong": 1})}}],
            },
        }
    ],
    "usage": {
        "prompt_tokens": _ANSWER_INPUT_TOKENS,
        "completion_tokens": _ANSWER_OUTPUT_TOKENS,
        "total_tokens": _ANSWER_INPUT_TOKENS + _ANSWER_OUTPUT_TOKENS,
    },
}
_ANTHROPIC_INVALID_ANSWER: dict[str, Any] = {
    "id": "msg_invalid",
    "type": "message",
    "role": "assistant",
    "model": "claude-test-2026",
    "content": [{"type": "tool_use", "id": "toolu_1", "name": "DummySchema", "input": {"wrong": 1}}],
    "stop_reason": "tool_use",
    "stop_sequence": None,
    "usage": {"input_tokens": _ANSWER_INPUT_TOKENS, "output_tokens": _ANSWER_OUTPUT_TOKENS},
}


def _read_openai_answer(*, response: Any) -> NbTokensByCategoryDict | None:
    """The tokens an OpenAI chat completion reports, read as the OpenAI completions worker reads them."""
    return object.__new__(OpenAICompletionsFactory).make_nb_tokens_by_category(usage=response.usage)


def _read_anthropic_answer(*, response: Any) -> NbTokensByCategoryDict | None:
    """The tokens an Anthropic message reports, read as the Anthropic worker reads them."""
    return AnthropicFactory.make_nb_tokens_by_category(usage=response.usage)


def _read_no_usage(*, response: Any) -> NbTokensByCategoryDict | None:
    """A provider whose answers report no usage."""
    del response
    return None


class _InvalidAnswers:
    """Answers every request with the same billable invalid answer, and counts the requests."""

    def __init__(self, *, body: dict[str, Any]) -> None:
        self.body = body
        self.nb_requests = 0

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.nb_requests += 1
        return httpx.Response(status_code=200, json=self.body, request=request)


@pytest.mark.asyncio(loop_scope="class")
class TestStructuredGenerationSpentReasks:
    @pytest.mark.parametrize("make_worker", _WORKERS)
    async def test_a_spent_reask_budget_reports_every_attempts_tokens_and_cost_on_the_failed_generation(
        self, mocker: MockerFixture, span_exporter: InMemorySpanExporter, make_worker: Callable[[MockerFixture], LLMWorkerAbstract]
    ) -> None:
        worker = make_worker(mocker)
        llm_job = _object_job()

        with pytest.raises(CogtError):
            await worker.gen_object(llm_job=llm_job, schema=DummySchema)

        (span,) = span_exporter.get_finished_spans()
        _assert_spent_reasks_on(span)
        assert llm_job.job_report.attempt_count == _MAX_ATTEMPTS
        tokens_usage = llm_job.job_report.llm_tokens_usage
        assert tokens_usage is not None
        assert tokens_usage.nb_tokens_by_category[TokenCategory.INPUT] == _SPENT_INPUT_TOKENS
        assert tokens_usage.nb_tokens_by_category[TokenCategory.OUTPUT] == _SPENT_OUTPUT_TOKENS

    @pytest.mark.parametrize("make_worker", _WORKERS)
    async def test_a_spent_reask_budget_is_reported_once_to_the_runs_cost_report(
        self, mocker: MockerFixture, span_exporter: InMemorySpanExporter, make_worker: Callable[[MockerFixture], LLMWorkerAbstract]
    ) -> None:
        """The provider billed every attempt: the failed generation reaches the reporting delegate once, with what they spent."""
        worker = make_worker(mocker)
        reporting_delegate = mocker.MagicMock(spec=ReportingProtocol)
        worker.reporting_delegate = reporting_delegate
        llm_job = _object_job()

        with pytest.raises(CogtError):
            await worker.gen_object(llm_job=llm_job, schema=DummySchema)

        reporting_delegate.report_inference_job.assert_called_once_with(inference_job=llm_job)
        assert llm_job.job_metadata.completed_at is not None
        tokens_usage = llm_job.job_report.llm_tokens_usage
        assert tokens_usage is not None
        assert tokens_usage.nb_tokens_by_category[TokenCategory.INPUT] == _SPENT_INPUT_TOKENS
        assert tokens_usage.nb_tokens_by_category[TokenCategory.OUTPUT] == _SPENT_OUTPUT_TOKENS
        (span,) = span_exporter.get_finished_spans()
        _assert_spent_reasks_on(span)

    async def test_openai_answers_are_summed_once_each(self) -> None:
        answers = _InvalidAnswers(body=_OPENAI_INVALID_ANSWER)
        attempts = InstructorAttempts(read_nb_tokens=_read_openai_answer)
        async with httpx.AsyncClient(transport=httpx.MockTransport(answers.handle)) as http_client:
            client = openai.AsyncOpenAI(
                api_key="unused-in-this-test", base_url="https://gateway.example.com/v1", max_retries=0, http_client=http_client
            )
            with pytest.raises(InstructorRetryException):
                await from_openai(client, mode=Mode.TOOLS).chat.completions.create_with_completion(
                    model="gpt-test-2026",
                    messages=[{"role": "user", "content": "Generate a structured object."}],
                    response_model=DummySchema,
                    max_retries=make_instructor_schema_retrying(max_attempts=_MAX_ATTEMPTS),
                    hooks=attempts.make_hooks(),
                )

        assert answers.nb_requests == attempts.attempt_count == _MAX_ATTEMPTS
        assert attempts.nb_tokens_by_category[TokenCategory.INPUT] == _SPENT_INPUT_TOKENS
        assert attempts.nb_tokens_by_category[TokenCategory.OUTPUT] == _SPENT_OUTPUT_TOKENS

    async def test_anthropic_answers_are_summed_once_each(self) -> None:
        answers = _InvalidAnswers(body=_ANTHROPIC_INVALID_ANSWER)
        attempts = InstructorAttempts(read_nb_tokens=_read_anthropic_answer)
        async with httpx.AsyncClient(transport=httpx.MockTransport(answers.handle)) as http_client:
            client = anthropic.AsyncAnthropic(
                api_key="unused-in-this-test", base_url="https://gateway.example.com", max_retries=0, http_client=http_client
            )
            with pytest.raises(InstructorRetryException):
                await from_anthropic(client).messages.create_with_completion(
                    model="claude-test-2026",
                    max_tokens=64,
                    messages=[{"role": "user", "content": "Generate a structured object."}],
                    response_model=DummySchema,
                    max_retries=make_instructor_schema_retrying(max_attempts=_MAX_ATTEMPTS),
                    hooks=attempts.make_hooks(),
                )

        assert answers.nb_requests == attempts.attempt_count == _MAX_ATTEMPTS
        assert attempts.nb_tokens_by_category[TokenCategory.INPUT] == _SPENT_INPUT_TOKENS
        assert attempts.nb_tokens_by_category[TokenCategory.OUTPUT] == _SPENT_OUTPUT_TOKENS

    async def test_answers_reporting_no_usage_leave_the_reports_usage_alone(self) -> None:
        """A provider whose answers report no usage keeps the usage its worker reads after the call; the attempts are counted still."""
        attempts = InstructorAttempts(read_nb_tokens=_read_no_usage)
        hooks = attempts.make_hooks()
        for _ in range(_MAX_ATTEMPTS):
            hooks.emit_completion_arguments(model="gpt-test-2026")
            hooks.emit_completion_response(SimpleNamespace())
        llm_job = _object_job()
        llm_job.llm_job_before_start(inference_model=_model(sdk="openai", model_id="gpt-test-2026"))
        tokens_usage = llm_job.job_report.llm_tokens_usage
        assert tokens_usage is not None
        tokens_usage.nb_tokens_by_category = {TokenCategory.INPUT: 7, TokenCategory.OUTPUT: 2}

        attempts.record_into(llm_job=llm_job)

        assert not attempts.has_usage
        assert llm_job.job_report.attempt_count == _MAX_ATTEMPTS
        assert tokens_usage.nb_tokens_by_category == {TokenCategory.INPUT: 7, TokenCategory.OUTPUT: 2}
