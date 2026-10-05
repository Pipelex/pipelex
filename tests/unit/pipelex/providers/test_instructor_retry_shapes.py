"""What ``instructor``'s real retry loop raises, pinned against the recovery and the test helper.

Every structured-output call goes through ``instructor``, which raises an
``InstructorRetryException`` from whatever ended its loop, and the workers recover
the SDK exception from that wrapper to classify it. The worker tests build the
wrapper by hand with ``wrap_in_instructor_retry``, and a hand-built wrapper is how
an earlier ``instructor`` release changed that shape with every worker test still
green. So this module drives the real loop instead: real ``from_openai`` and
``from_anthropic`` factories, over real SDK clients whose transport is an
``httpx.MockTransport``, with the schema-only retrying the workers pass.

Three shapes end the loop: an API error on the first attempt, an invalid output
re-asked and then an API error, and a re-ask budget spent on invalid outputs. For
each, the recovery must return the exception that ended the loop, and the two API
error shapes must be the shape the helper builds.

The Anthropic SDK release locked here takes an ``httpx`` client; later releases take
``httpx2``, so a lock move there changes how the transport is handed over.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import anthropic
import httpx
import openai
import pytest
from instructor import Mode, from_anthropic, from_openai
from instructor.core import FailedAttempt, InstructorRetryException
from pydantic import ValidationError
from tenacity import RetryError

from pipelex.base_exceptions import ErrorDomain
from pipelex.cogt.exceptions import InferenceErrorCategory, LLMCompletionError, LLMModelNotFoundError
from pipelex.cogt.inference.error_classification import UserActionKind, extract_underlying_sdk_exception
from pipelex.cogt.llm.instructor_retry import make_instructor_schema_retrying
from pipelex.pipe_run.exceptions import PipeRouterError
from pipelex.providers.openai.openai_completions_llm_worker import OpenAICompletionsLLMWorker
from pipelex.system.pipe_run_mode import PipeRunMode
from tests.helpers.instructor_test_utils import DummySchema, make_llm_job, wrap_in_instructor_retry

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from pytest_mock import MockerFixture

_ORIGIN = "https://gateway.example.com"
_MAX_ATTEMPTS = 3

# A scripted HTTP answer: the status and the JSON body.
_ScriptedResponse = tuple[int, dict[str, Any]]

# The refusal a run on the hosted API received, verbatim, and the handle its method named.
_WIRE_ID = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
_MODEL_HANDLE = "claude-4.5-sonnet"
_MODEL_NOT_ALLOWED: _ScriptedResponse = (
    412,
    {"error": {"message": f"Model {_WIRE_ID} is not allowed for this integration", "type": "model_not_allowed_error", "param": None, "code": None}},
)

_OPENAI_RATE_LIMIT: _ScriptedResponse = (429, {"error": {"message": "Rate limit reached", "type": "rate_limit_error", "code": "rate_limit_exceeded"}})
_ANTHROPIC_RATE_LIMIT: _ScriptedResponse = (429, {"type": "error", "error": {"type": "rate_limit_error", "message": "Rate limit reached"}})

# A tool call whose arguments fail ``DummySchema``, which requires ``text``.
_INVALID_ARGUMENTS: dict[str, Any] = {"wrong": 1}

_OPENAI_INVALID_OUTPUT: _ScriptedResponse = (
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
                    "tool_calls": [
                        {"id": "call_1", "type": "function", "function": {"name": "DummySchema", "arguments": json.dumps(_INVALID_ARGUMENTS)}}
                    ],
                },
            }
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    },
)
_ANTHROPIC_INVALID_OUTPUT: _ScriptedResponse = (
    200,
    {
        "id": "msg_invalid",
        "type": "message",
        "role": "assistant",
        "model": "some-model",
        "content": [{"type": "tool_use", "id": "toolu_1", "name": "DummySchema", "input": _INVALID_ARGUMENTS}],
        "stop_reason": "tool_use",
        "stop_sequence": None,
        "usage": {"input_tokens": 1, "output_tokens": 1},
    },
)


class _ScriptedTransport:
    """Answers each request with the next scripted response, and counts the requests."""

    def __init__(self, responses: list[_ScriptedResponse]) -> None:
        self.responses = list(responses)
        self.nb_requests = 0

    def handle(self, request: httpx.Request) -> httpx.Response:
        scripted_response = self.responses[self.nb_requests]
        self.nb_requests += 1
        status_code, body = scripted_response
        return httpx.Response(status_code=status_code, json=body, request=request)

    def make_http_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(self.handle))


def _failed_attempts_of(raised: InstructorRetryException) -> list[FailedAttempt]:
    """The attempts instructor recorded as failed, which the real loop always sets, empty or not."""
    failed_attempts = raised.failed_attempts
    assert failed_attempts is not None
    return failed_attempts


async def _raised_by_openai(transport: _ScriptedTransport) -> InstructorRetryException:
    """Drive ``from_openai``'s loop to its end, the way the OpenAI completions worker calls it."""
    async with transport.make_http_client() as http_client:
        client = openai.AsyncOpenAI(api_key="unused-in-this-test", base_url=f"{_ORIGIN}/v1", max_retries=0, http_client=http_client)
        structured = from_openai(client, mode=Mode.TOOLS)
        with pytest.raises(InstructorRetryException) as exc_info:
            await structured.chat.completions.create_with_completion(
                model="some-model",
                messages=[{"role": "user", "content": "Generate a structured object."}],
                response_model=DummySchema,
                max_retries=make_instructor_schema_retrying(max_attempts=_MAX_ATTEMPTS),
            )
    return exc_info.value


async def _raised_by_anthropic(transport: _ScriptedTransport) -> InstructorRetryException:
    """Drive ``from_anthropic``'s loop to its end, the way the Anthropic worker calls it."""
    async with transport.make_http_client() as http_client:
        client = anthropic.AsyncAnthropic(api_key="unused-in-this-test", base_url=_ORIGIN, max_retries=0, http_client=http_client)
        structured = from_anthropic(client)
        with pytest.raises(InstructorRetryException) as exc_info:
            await structured.messages.create_with_completion(
                model="some-model",
                max_tokens=64,
                messages=[{"role": "user", "content": "Generate a structured object."}],
                response_model=DummySchema,
                max_retries=make_instructor_schema_retrying(max_attempts=_MAX_ATTEMPTS),
            )
    return exc_info.value


# The two shapes an API error ends: on the first attempt, and after a re-ask. Each
# names the driver, the script, the SDK exception class that must end the loop, and
# how many parse failures instructor must have recorded before it.
_API_ERROR_SHAPES = [
    pytest.param(_raised_by_openai, [_MODEL_NOT_ALLOWED], openai.APIStatusError, 0, id="openai-api-error-first"),
    pytest.param(_raised_by_openai, [_OPENAI_INVALID_OUTPUT, _OPENAI_RATE_LIMIT], openai.RateLimitError, 1, id="openai-invalid-then-api-error"),
    pytest.param(_raised_by_anthropic, [_ANTHROPIC_RATE_LIMIT], anthropic.RateLimitError, 0, id="anthropic-api-error-first"),
    pytest.param(
        _raised_by_anthropic, [_ANTHROPIC_INVALID_OUTPUT, _ANTHROPIC_RATE_LIMIT], anthropic.RateLimitError, 1, id="anthropic-invalid-then-api-error"
    ),
]

_SPENT_BUDGET_SHAPES = [
    pytest.param(_raised_by_openai, [_OPENAI_INVALID_OUTPUT] * _MAX_ATTEMPTS, id="openai-budget-spent"),
    pytest.param(_raised_by_anthropic, [_ANTHROPIC_INVALID_OUTPUT] * _MAX_ATTEMPTS, id="anthropic-budget-spent"),
]


@pytest.mark.asyncio(loop_scope="class")
class TestInstructorRetryShapes:
    @pytest.mark.parametrize(("raised_by", "responses", "sdk_exception_class", "nb_parse_failures"), _API_ERROR_SHAPES)
    async def test_an_api_error_ends_the_loop_on_the_cause_and_is_what_the_recovery_returns(
        self,
        raised_by: Callable[[_ScriptedTransport], Awaitable[InstructorRetryException]],
        responses: list[_ScriptedResponse],
        sdk_exception_class: type[Exception],
        nb_parse_failures: int,
    ) -> None:
        """The SDK exception sits on ``__cause__`` alone; ``failed_attempts`` lists only the parse failures before it."""
        transport = _ScriptedTransport(responses)

        raised = await raised_by(transport)

        assert transport.nb_requests == len(responses)
        assert isinstance(raised.__cause__, sdk_exception_class)
        assert [type(failed_attempt.exception) for failed_attempt in _failed_attempts_of(raised)] == [ValidationError] * nb_parse_failures
        assert extract_underlying_sdk_exception(raised) is raised.__cause__

    @pytest.mark.parametrize(("raised_by", "responses", "sdk_exception_class", "nb_parse_failures"), _API_ERROR_SHAPES)
    async def test_the_helper_builds_the_shape_the_real_loop_raises(
        self,
        raised_by: Callable[[_ScriptedTransport], Awaitable[InstructorRetryException]],
        responses: list[_ScriptedResponse],
        sdk_exception_class: type[Exception],
        nb_parse_failures: int,
    ) -> None:
        """``wrap_in_instructor_retry``, fed what the real loop saw, must build what the real loop raised.

        Every worker test builds its wrapper with that helper, so this is what keeps
        those tests honest across an ``instructor`` release that changes the shape.
        """
        raised = await raised_by(_ScriptedTransport(responses))
        sdk_exc = raised.__cause__
        assert isinstance(sdk_exc, sdk_exception_class)
        parse_failures = [failed_attempt.exception for failed_attempt in _failed_attempts_of(raised)]
        assert len(parse_failures) == nb_parse_failures

        built = wrap_in_instructor_retry(sdk_exc, earlier_parse_failures=parse_failures)

        assert built.__cause__ is raised.__cause__
        assert [(attempt.attempt_number, attempt.exception) for attempt in _failed_attempts_of(built)] == [
            (attempt.attempt_number, attempt.exception) for attempt in _failed_attempts_of(raised)
        ]
        assert built.n_attempts == raised.n_attempts
        assert extract_underlying_sdk_exception(built) is extract_underlying_sdk_exception(raised)

    @pytest.mark.parametrize(("raised_by", "responses"), _SPENT_BUDGET_SHAPES)
    async def test_a_spent_budget_recovers_the_last_parse_failure(
        self,
        raised_by: Callable[[_ScriptedTransport], Awaitable[InstructorRetryException]],
        responses: list[_ScriptedResponse],
    ) -> None:
        """Once the re-ask budget is spent the cause is tenacity's ``RetryError``, whose last attempt holds the final parse failure."""
        transport = _ScriptedTransport(responses)

        raised = await raised_by(transport)

        assert transport.nb_requests == _MAX_ATTEMPTS
        assert isinstance(raised.__cause__, RetryError)
        failed_attempts = _failed_attempts_of(raised)
        assert len(failed_attempts) == _MAX_ATTEMPTS
        recovered = extract_underlying_sdk_exception(raised)
        assert isinstance(recovered, ValidationError)
        assert recovered is failed_attempts[-1].exception

    async def test_a_gateway_model_not_allowed_refusal_reaches_the_run_report_as_change_model(self, mocker: MockerFixture) -> None:
        """The run the refusal was first seen on, end to end: the worker over real instructor, then the pipe's location.

        That run read ``error_category: unknown`` and a user action saying only that
        the message gives the cause. It must read as a configuration error whose
        next step is another model, named as the method named it, and it must not
        be retried or re-asked.
        """
        transport = _ScriptedTransport([_MODEL_NOT_ALLOWED])
        worker = object.__new__(OpenAICompletionsLLMWorker)
        inference_model = mocker.MagicMock()
        inference_model.name = _MODEL_HANDLE
        inference_model.model_id = _WIRE_ID
        inference_model.desc = f"{_MODEL_HANDLE} → SDK[pipelex_hosted_completions]•Backend[pipelex_hosted]•Model[{_WIRE_ID}]"
        inference_model.thinking_mode = None
        inference_model.listed_constraints = []
        worker.inference_model = inference_model
        completions_factory = mocker.MagicMock()
        completions_factory.make_simple_messages = mocker.AsyncMock(return_value=[{"role": "user", "content": "Score this lead."}])
        completions_factory.make_extras = mocker.MagicMock(return_value=({}, {}))
        worker.openai_completions_factory = completions_factory
        llm_job = make_llm_job(mocker)
        llm_job.job_params.seed = None
        llm_job.job_config.schema_reask_max_attempts = _MAX_ATTEMPTS

        async with transport.make_http_client() as http_client:
            client = openai.AsyncOpenAI(api_key="unused-in-this-test", base_url=f"{_ORIGIN}/v1", max_retries=0, http_client=http_client)
            worker.instructor_for_objects = from_openai(client, mode=Mode.TOOLS)
            with pytest.raises(LLMCompletionError) as exc_info:
                await worker._gen_object(llm_job=llm_job, schema=DummySchema)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        failure = exc_info.value
        assert transport.nb_requests == 1
        assert not isinstance(failure, LLMModelNotFoundError)
        assert failure.provider_metadata is not None
        assert failure.provider_metadata.status_code == 412
        assert failure.provider_metadata.is_model_not_allowed

        located = PipeRouterError.make_located(
            failure=failure,
            run_mode=PipeRunMode.LIVE,
            pipe_code="score_lead",
            output_name=None,
            pipe_stack=["score_lead"],
        )
        located.__cause__ = failure
        report = located.to_error_report()

        assert report.error_type == "LLMCompletionError"
        assert report.error_domain == ErrorDomain.CONFIG
        assert report.error_category == InferenceErrorCategory.CONFIGURATION
        assert report.retryable is False
        assert report.http_status == 500
        assert report.user_action is not None
        assert report.user_action.kind == UserActionKind.CHANGE_MODEL
        assert f"'{_MODEL_HANDLE}'" in report.user_action.detail
        assert _WIRE_ID not in report.user_action.detail
        assert report.message.startswith("Pipe 'score_lead' failed: ")
