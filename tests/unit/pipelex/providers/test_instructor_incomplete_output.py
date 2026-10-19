# A structured output cut at its output limit reads `model.output_truncated`, driven through instructor's real loop.
#
# instructor reads the stop value of every structured answer it parses and raises its `IncompleteOutputException` for
# one cut at the request's output limit: an OpenAI or Mistral completion whose first choice finished on `length`, an
# Anthropic message that stopped on `max_tokens`. Its re-asks never retry it and it is never wrapped in an
# `InstructorRetryException`, so it escaped every worker as an exception nothing classified, `runtime.unexpected`.
#
# This module drives each worker whose structuring mode can raise it, the Anthropic, OpenAI completions and Mistral
# workers, over a real SDK client whose transport is an `httpx.MockTransport` answering with the provider's own cut
# answer, and through instructor's real loop with the schema-only retrying the workers pass. Gemini's and the Responses
# API's structuring modes never raise it, so their workers are not driven here.

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import anthropic
import httpx
import openai
import pytest
from instructor import Mode, from_anthropic, from_mistral, from_openai
from instructor.core import IncompleteOutputException
from mistralai.client import Mistral
from mthds.protocol.problem.registry import CoreCode

from pipelex.cogt.exceptions import CompletionOutputKind, CompletionTruncationLimit, LLMCompletionTruncatedError, MaxTokensCeiling
from pipelex.cogt.llm.instructor_retry import make_instructor_schema_retrying
from pipelex.providers.anthropic.anthropic_llm_worker import AnthropicLLMWorker
from pipelex.providers.mistral.mistral_llm_worker import MistralLLMWorker
from pipelex.providers.openai.openai_completions_llm_worker import OpenAICompletionsLLMWorker
from tests.helpers.completion_stop import STOP_TEST_PARTIAL_TEXT, STOP_TEST_PIPE_CODE, make_text_llm_job
from tests.helpers.instructor_test_utils import DummySchema

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

    from pipelex.cogt.llm.llm_job import LLMJob

_ORIGIN = "https://provider.example.com"
_MAX_TOKENS = 64
_OUTPUT_TOKENS = 64
_MAX_ATTEMPTS = 2

# A scripted HTTP answer: the status and the JSON body.
_ScriptedResponse = tuple[int, dict[str, Any]]

# The tool call's arguments as the model left them when the limit cut it: JSON that does not close.
_CUT_ARGUMENTS = '{"text": "' + STOP_TEST_PARTIAL_TEXT

_OPENAI_CUT_ANSWER: _ScriptedResponse = (
    200,
    {
        "id": "chatcmpl-cut",
        "object": "chat.completion",
        "created": 0,
        "model": "some-model",
        "choices": [
            {
                "index": 0,
                "finish_reason": "length",
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "DummySchema", "arguments": _CUT_ARGUMENTS}}],
                },
            }
        ],
        "usage": {"prompt_tokens": 12, "completion_tokens": _OUTPUT_TOKENS, "total_tokens": 12 + _OUTPUT_TOKENS},
    },
)

_ANTHROPIC_CUT_ANSWER: _ScriptedResponse = (
    200,
    {
        "id": "msg_cut",
        "type": "message",
        "role": "assistant",
        "model": "some-model",
        "content": [{"type": "tool_use", "id": "toolu_1", "name": "DummySchema", "input": {}}],
        "stop_reason": "max_tokens",
        "stop_sequence": None,
        "usage": {"input_tokens": 12, "output_tokens": _OUTPUT_TOKENS},
    },
)

_MISTRAL_CUT_ANSWER: _ScriptedResponse = (
    200,
    {
        "id": "cmpl-cut",
        "object": "chat.completion",
        "created": 0,
        "model": "mistral-large-latest",
        "choices": [
            {
                "index": 0,
                "finish_reason": "length",
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [{"id": "call1", "type": "function", "function": {"name": "DummySchema", "arguments": _CUT_ARGUMENTS}}],
                },
            }
        ],
        "usage": {"prompt_tokens": 12, "completion_tokens": _OUTPUT_TOKENS, "total_tokens": 12 + _OUTPUT_TOKENS},
    },
)

# An answer whose tool call fails `DummySchema`, which requires `text`: instructor re-asks it.
_OPENAI_INVALID_ANSWER: _ScriptedResponse = (
    200,
    {
        "id": "chatcmpl-invalid",
        "object": "chat.completion",
        "created": 0,
        "model": "some-model",
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
        "usage": {"prompt_tokens": 12, "completion_tokens": 4, "total_tokens": 16},
    },
)


class _ScriptedTransport:
    """Answers each request with the next scripted response, and counts the requests."""

    def __init__(self, responses: list[_ScriptedResponse]) -> None:
        self.responses = list(responses)
        self.nb_requests = 0

    def handle(self, request: httpx.Request) -> httpx.Response:
        status_code, body = self.responses[self.nb_requests]
        self.nb_requests += 1
        return httpx.Response(status_code=status_code, json=body, request=request)

    def make_http_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(self.handle))


def _assert_names_a_structured_output(error: LLMCompletionTruncatedError) -> None:
    """The error says a structured output was cut, never a text."""
    assert error.output_kind == CompletionOutputKind.STRUCTURED
    assert f"finished the structured output of pipe '{STOP_TEST_PIPE_CODE}'" in error.message
    assert "so the structured output is incomplete" in error.message
    assert "text" not in error.message


def _structured_job(*, max_tokens: int | None) -> LLMJob:
    """A real job for the pipe the stop tests name, re-asking once, as a structured output's job does."""
    llm_job = make_text_llm_job(max_tokens=max_tokens)
    llm_job.job_config.schema_reask_max_attempts = _MAX_ATTEMPTS
    return llm_job


def _inference_model(mocker: MockerFixture, *, name: str, model_id: str) -> Any:
    inference_model = mocker.MagicMock()
    inference_model.name = name
    inference_model.model_id = model_id
    inference_model.desc = f"{name} → Model[{model_id}]"
    inference_model.thinking_mode = None
    inference_model.accepts_temperature = True
    inference_model.max_tokens = 4096
    inference_model.listed_constraints = []
    return inference_model


def _openai_worker(mocker: MockerFixture, *, http_client: httpx.AsyncClient) -> OpenAICompletionsLLMWorker:
    worker = object.__new__(OpenAICompletionsLLMWorker)
    worker.inference_model = _inference_model(mocker, name="gpt-4o", model_id="gpt-4o-2024-08-06")
    completions_factory = mocker.MagicMock()
    completions_factory.make_simple_messages = mocker.AsyncMock(return_value=[{"role": "user", "content": "Summarize the contract."}])
    completions_factory.make_extras = mocker.MagicMock(return_value=({}, {}))
    worker.openai_completions_factory = completions_factory
    client = openai.AsyncOpenAI(api_key="unused-in-this-test", base_url=f"{_ORIGIN}/v1", max_retries=0, http_client=http_client)
    worker.instructor_for_objects = from_openai(client, mode=Mode.TOOLS)
    return worker


def _anthropic_worker(mocker: MockerFixture, *, http_client: httpx.AsyncClient) -> AnthropicLLMWorker:
    worker = object.__new__(AnthropicLLMWorker)
    worker.extras_factory = None
    worker.inference_model = _inference_model(mocker, name="claude-4.5-sonnet", model_id="claude-sonnet-4-5-20250929")
    worker.default_max_tokens = 4096
    client = anthropic.AsyncAnthropic(api_key="unused-in-this-test", base_url=_ORIGIN, max_retries=0, http_client=http_client)
    worker.instructor_for_objects = from_anthropic(client)
    config = mocker.MagicMock()
    config.inference.llm.anthropic.structured_output_timeout_seconds = 1200
    mocker.patch("pipelex.providers.anthropic.anthropic_llm_worker.get_config", return_value=config)
    mocker.patch(
        "pipelex.providers.anthropic.anthropic_llm_worker.AnthropicFactory.make_simple_messages",
        new=mocker.AsyncMock(return_value=[{"role": "user", "content": "Summarize the contract."}]),
    )
    return worker


def _mistral_worker(mocker: MockerFixture, *, http_client: httpx.AsyncClient) -> MistralLLMWorker:
    worker = object.__new__(MistralLLMWorker)
    worker.inference_model = _inference_model(mocker, name="mistral-large", model_id="mistral-large-latest")
    worker.default_max_tokens = 4096
    mistral_factory = mocker.MagicMock()
    mistral_factory.make_simple_messages_openai_typed = mocker.AsyncMock(return_value=[{"role": "user", "content": "Summarize the contract."}])
    worker.mistral_factory = mistral_factory
    client = Mistral(api_key="unused-in-this-test", server_url=_ORIGIN, async_client=http_client)
    worker.instructor_for_objects = from_mistral(client=client, mode=Mode.TOOLS, use_async=True)
    return worker


@pytest.mark.asyncio(loop_scope="class")
class TestInstructorIncompleteOutput:
    async def test_instructor_raises_the_cut_answer_unwrapped(self) -> None:
        """The shape the workers catch: instructor's own exception, carrying the cut answer, never its retry wrapper."""
        transport = _ScriptedTransport([_OPENAI_CUT_ANSWER])
        async with transport.make_http_client() as http_client:
            client = openai.AsyncOpenAI(api_key="unused-in-this-test", base_url=f"{_ORIGIN}/v1", max_retries=0, http_client=http_client)
            structured = from_openai(client, mode=Mode.TOOLS)
            with pytest.raises(IncompleteOutputException) as exc_info:
                await structured.chat.completions.create_with_completion(
                    model="some-model",
                    messages=[{"role": "user", "content": "Summarize the contract."}],
                    response_model=DummySchema,
                    max_retries=make_instructor_schema_retrying(max_attempts=_MAX_ATTEMPTS),
                )

        assert transport.nb_requests == 1
        assert type(exc_info.value) is IncompleteOutputException
        last_completion = exc_info.value.last_completion
        assert last_completion is not None
        assert last_completion.choices[0].finish_reason == "length"

    async def test_the_openai_completions_worker_reads_the_cut_as_output_truncated(self, mocker: MockerFixture) -> None:
        transport = _ScriptedTransport([_OPENAI_CUT_ANSWER])
        async with transport.make_http_client() as http_client:
            worker = _openai_worker(mocker, http_client=http_client)
            with pytest.raises(LLMCompletionTruncatedError) as exc_info:
                await worker._gen_object(llm_job=_structured_job(max_tokens=_MAX_TOKENS), schema=DummySchema)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        error = exc_info.value
        assert transport.nb_requests == 1
        assert error.resolve_error_code() == CoreCode.MODEL_OUTPUT_TRUNCATED
        assert error.truncation_limit == CompletionTruncationLimit.MAX_TOKENS
        assert error.stop_reason == "length"
        assert error.pipe_code == STOP_TEST_PIPE_CODE
        assert error.max_tokens == _MAX_TOKENS
        assert error.output_tokens == _OUTPUT_TOKENS
        assert isinstance(error.__cause__, IncompleteOutputException)
        assert STOP_TEST_PARTIAL_TEXT not in error.message
        _assert_names_a_structured_output(error)

    async def test_a_cut_after_a_re_ask_is_still_the_truncation(self, mocker: MockerFixture) -> None:
        """A re-asked answer that comes back cut ends the loop with the same exception, which no wrapper hides."""
        transport = _ScriptedTransport([_OPENAI_INVALID_ANSWER, _OPENAI_CUT_ANSWER])
        async with transport.make_http_client() as http_client:
            worker = _openai_worker(mocker, http_client=http_client)
            with pytest.raises(LLMCompletionTruncatedError) as exc_info:
                await worker._gen_object(llm_job=_structured_job(max_tokens=None), schema=DummySchema)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        error = exc_info.value
        assert transport.nb_requests == 2
        assert error.resolve_error_code() == CoreCode.MODEL_OUTPUT_TRUNCATED
        # The request sent no max_tokens, so the next step sets one rather than raising it
        assert error.max_tokens is None
        assert "no max_tokens sent" in error.message

    async def test_the_anthropic_worker_reads_the_cut_as_output_truncated(self, mocker: MockerFixture) -> None:
        transport = _ScriptedTransport([_ANTHROPIC_CUT_ANSWER])
        async with transport.make_http_client() as http_client:
            worker = _anthropic_worker(mocker, http_client=http_client)
            with pytest.raises(LLMCompletionTruncatedError) as exc_info:
                await worker._gen_object(llm_job=_structured_job(max_tokens=_MAX_TOKENS), schema=DummySchema)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        error = exc_info.value
        assert transport.nb_requests == 1
        assert error.resolve_error_code() == CoreCode.MODEL_OUTPUT_TRUNCATED
        assert error.stop_reason == "max_tokens"
        assert error.pipe_code == STOP_TEST_PIPE_CODE
        assert error.max_tokens == _MAX_TOKENS
        assert error.output_tokens == _OUTPUT_TOKENS
        assert isinstance(error.__cause__, IncompleteOutputException)
        _assert_names_a_structured_output(error)
        # The limit sent is the one asked for, so raising it is the next step
        assert error.max_tokens_ceiling is None
        assert error.user_action is not None
        assert error.user_action.detail == "Raise the pipe's max_tokens, or shorten its input."

    async def test_the_anthropic_worker_says_its_timeout_lowered_the_limit_that_cut(self, mocker: MockerFixture) -> None:
        """A limit the structured call lowered to fit its timeout can explain the cut, so the error says so."""
        transport = _ScriptedTransport([_ANTHROPIC_CUT_ANSWER])
        async with transport.make_http_client() as http_client:
            worker = _anthropic_worker(mocker, http_client=http_client)
            mocker.patch(
                "pipelex.providers.anthropic.anthropic_llm_worker.AnthropicFactory.calculate_safe_max_tokens_for_timeout",
                return_value=_MAX_TOKENS,
            )
            with pytest.raises(LLMCompletionTruncatedError) as exc_info:
                await worker._gen_object(llm_job=_structured_job(max_tokens=8192), schema=DummySchema)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        error = exc_info.value
        assert error.resolve_error_code() == CoreCode.MODEL_OUTPUT_TRUNCATED
        assert error.max_tokens == _MAX_TOKENS
        assert error.max_tokens_ceiling == MaxTokensCeiling(requested_max_tokens=8192, timeout_seconds=1200)
        assert f"lowered from 8192 to {_MAX_TOKENS}" in error.message
        assert error.message.count("lowered from") == 1
        # A higher max_tokens is lowered the same way, so neither the message nor the action asks for one
        next_step = "Lower the pipe's reasoning effort, or ask it for a smaller output, since a higher max_tokens is lowered the same way."
        assert error.message.endswith(next_step)
        assert "Raise" not in error.message
        assert error.user_action is not None
        assert error.user_action.detail == next_step

    async def test_the_mistral_worker_reads_the_cut_as_output_truncated(self, mocker: MockerFixture) -> None:
        transport = _ScriptedTransport([_MISTRAL_CUT_ANSWER])
        async with transport.make_http_client() as http_client:
            worker = _mistral_worker(mocker, http_client=http_client)
            with pytest.raises(LLMCompletionTruncatedError) as exc_info:
                await worker._gen_object(llm_job=_structured_job(max_tokens=_MAX_TOKENS), schema=DummySchema)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        error = exc_info.value
        assert transport.nb_requests == 1
        assert error.resolve_error_code() == CoreCode.MODEL_OUTPUT_TRUNCATED
        assert error.stop_reason == "length"
        assert error.pipe_code == STOP_TEST_PIPE_CODE
        assert error.max_tokens == _MAX_TOKENS
        assert error.output_tokens == _OUTPUT_TOKENS
        assert isinstance(error.__cause__, IncompleteOutputException)
        _assert_names_a_structured_output(error)
