"""Tests for OpenAI Completions worker structured-generation error handling.

Verifies that ``_gen_object`` correctly unwraps ``InstructorRetryException`` to
recover the underlying OpenAI SDK exception, attaches ``ProviderErrorMetadata``,
and surfaces semantic ``UserActionKind`` values — so transient/capacity/auth
errors are categorized correctly instead of being flattened to ``CONTENT``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx
import openai
import pytest

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

from pipelex.cogt.exceptions import InferenceErrorCategory, LLMCompletionError, LLMModelNotFoundError
from pipelex.cogt.inference.error_classification import UserActionKind
from pipelex.providers.openai.openai_completions_llm_worker import OpenAICompletionsLLMWorker
from tests.helpers.instructor_test_utils import DummySchema, make_llm_job, wrap_in_instructor_retry


def _mock_httpx_response(status_code: int, headers: dict[str, str] | None = None) -> httpx.Response:
    request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    return httpx.Response(status_code=status_code, request=request, headers=headers or {})


def _make_openai_rate_limit_error(message: str) -> openai.RateLimitError:
    return openai.RateLimitError(
        message,
        response=_mock_httpx_response(429, headers={"x-request-id": "req_rate", "retry-after": "3"}),
        body={"type": "rate_limit_error", "code": "rate_limit_exceeded", "message": message},
    )


def _make_openai_bad_request_error(message: str) -> openai.BadRequestError:
    return openai.BadRequestError(
        message,
        response=_mock_httpx_response(400, headers={"x-request-id": "req_bad"}),
        body={"type": "invalid_request_error", "code": "invalid_param", "message": message},
    )


def _make_openai_timeout_error() -> openai.APITimeoutError:
    request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    return openai.APITimeoutError(request=request)


def _make_openai_connection_error(message: str = "Connection refused") -> openai.APIConnectionError:
    request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    return openai.APIConnectionError(message=message, request=request)


def _make_openai_auth_error(message: str) -> openai.AuthenticationError:
    return openai.AuthenticationError(
        message,
        response=_mock_httpx_response(401, headers={"x-request-id": "req_auth"}),
        body={"type": "invalid_request_error", "code": "invalid_api_key", "message": message},
    )


def _make_openai_not_found_error(message: str) -> openai.NotFoundError:
    return openai.NotFoundError(
        message,
        response=_mock_httpx_response(404, headers={"x-request-id": "req_404"}),
        body={"type": "invalid_request_error", "code": "model_not_found", "message": message},
    )


def _make_worker(mocker: MockerFixture) -> OpenAICompletionsLLMWorker:
    worker = object.__new__(OpenAICompletionsLLMWorker)
    mock_model = mocker.MagicMock()
    mock_model.desc = "test-model-desc"
    mock_model.model_id = "gpt-4o"
    mock_model.name = "gpt-4o"
    mock_model.thinking_mode = None
    mock_model.listed_constraints = []
    worker.inference_model = mock_model

    instructor_client = mocker.MagicMock()
    instructor_client.chat.completions.create_with_completion = mocker.AsyncMock()
    worker.instructor_for_objects = instructor_client

    mock_factory = mocker.MagicMock()
    mock_factory.make_simple_messages = mocker.AsyncMock(return_value=[])
    mock_factory.make_extras = mocker.MagicMock(return_value=({}, {}))
    worker.openai_completions_factory = mock_factory

    return worker


@pytest.mark.asyncio(loop_scope="class")
class TestOpenAICompletionsWorkerObjectErrorHandling:
    """``_gen_object`` must categorize SDK errors that ``instructor`` wraps in ``InstructorRetryException``."""

    async def test_wrapped_rate_limit_is_transient(self, mocker: MockerFixture) -> None:
        worker = _make_worker(mocker)
        sdk_exc = _make_openai_rate_limit_error("Rate limit exceeded — please retry")
        wrapped = wrap_in_instructor_retry(sdk_exc)
        worker.instructor_for_objects.chat.completions.create_with_completion.side_effect = wrapped  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(LLMCompletionError) as exc_info:
            await worker._gen_object(llm_job=make_llm_job(mocker), schema=DummySchema)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.TRANSIENT
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.WAIT_AND_RETRY
        assert "run it again" in exc_info.value.user_action.detail
        assert exc_info.value.__cause__ is wrapped
        metadata = exc_info.value.provider_metadata
        assert metadata is not None
        assert metadata.provider == "openai"
        assert metadata.sdk_exception_type == "RateLimitError"
        assert metadata.status_code == 429
        assert metadata.request_id == "req_rate"
        assert metadata.retry_after_seconds == 3.0
        assert metadata.provider_error_code == "rate_limit_error"

    async def test_wrapped_rate_limit_quota_is_capacity(self, mocker: MockerFixture) -> None:
        worker = _make_worker(mocker)
        sdk_exc = _make_openai_rate_limit_error("Error: insufficient_quota — you exceeded your billing limit")
        wrapped = wrap_in_instructor_retry(sdk_exc)
        worker.instructor_for_objects.chat.completions.create_with_completion.side_effect = wrapped  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(LLMCompletionError) as exc_info:
            await worker._gen_object(llm_job=make_llm_job(mocker), schema=DummySchema)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.CAPACITY
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.CHECK_BILLING
        assert "billing" in exc_info.value.user_action.detail.lower()
        metadata = exc_info.value.provider_metadata
        assert metadata is not None
        assert metadata.status_code == 429
        assert metadata.sdk_exception_type == "RateLimitError"

    async def test_wrapped_timeout_is_transient(self, mocker: MockerFixture) -> None:
        worker = _make_worker(mocker)
        wrapped = wrap_in_instructor_retry(_make_openai_timeout_error())
        worker.instructor_for_objects.chat.completions.create_with_completion.side_effect = wrapped  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(LLMCompletionError) as exc_info:
            await worker._gen_object(llm_job=make_llm_job(mocker), schema=DummySchema)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.TRANSIENT
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.WAIT_AND_RETRY
        metadata = exc_info.value.provider_metadata
        assert metadata is not None
        assert metadata.sdk_exception_type == "APITimeoutError"
        assert metadata.status_code is None

    async def test_wrapped_connection_error_is_transient(self, mocker: MockerFixture) -> None:
        worker = _make_worker(mocker)
        wrapped = wrap_in_instructor_retry(_make_openai_connection_error())
        worker.instructor_for_objects.chat.completions.create_with_completion.side_effect = wrapped  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(LLMCompletionError) as exc_info:
            await worker._gen_object(llm_job=make_llm_job(mocker), schema=DummySchema)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.TRANSIENT
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.WAIT_AND_RETRY
        metadata = exc_info.value.provider_metadata
        assert metadata is not None
        assert metadata.sdk_exception_type == "APIConnectionError"

    async def test_wrapped_bad_request_content_policy(self, mocker: MockerFixture) -> None:
        worker = _make_worker(mocker)
        sdk_exc = _make_openai_bad_request_error("Your request was rejected due to content_policy_violation")
        wrapped = wrap_in_instructor_retry(sdk_exc)
        worker.instructor_for_objects.chat.completions.create_with_completion.side_effect = wrapped  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(LLMCompletionError) as exc_info:
            await worker._gen_object(llm_job=make_llm_job(mocker), schema=DummySchema)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.CONTENT
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.CHANGE_INPUT
        assert "safety filters" in exc_info.value.user_action.detail.lower()
        metadata = exc_info.value.provider_metadata
        assert metadata is not None
        assert metadata.status_code == 400
        assert metadata.sdk_exception_type == "BadRequestError"

    async def test_wrapped_bad_request_generic_is_content(self, mocker: MockerFixture) -> None:
        worker = _make_worker(mocker)
        sdk_exc = _make_openai_bad_request_error("Invalid parameter: temperature must be between 0 and 2")
        wrapped = wrap_in_instructor_retry(sdk_exc)
        worker.instructor_for_objects.chat.completions.create_with_completion.side_effect = wrapped  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(LLMCompletionError) as exc_info:
            await worker._gen_object(llm_job=make_llm_job(mocker), schema=DummySchema)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.CONTENT
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.CHANGE_INPUT
        metadata = exc_info.value.provider_metadata
        assert metadata is not None
        assert metadata.status_code == 400

    async def test_wrapped_auth_error_is_configuration(self, mocker: MockerFixture) -> None:
        worker = _make_worker(mocker)
        wrapped = wrap_in_instructor_retry(_make_openai_auth_error("Invalid API key"))
        worker.instructor_for_objects.chat.completions.create_with_completion.side_effect = wrapped  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(LLMCompletionError) as exc_info:
            await worker._gen_object(llm_job=make_llm_job(mocker), schema=DummySchema)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.CONFIGURATION
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.CHECK_CREDENTIALS
        metadata = exc_info.value.provider_metadata
        assert metadata is not None
        assert metadata.status_code == 401
        assert metadata.sdk_exception_type == "AuthenticationError"

    async def test_wrapped_not_found_is_configuration(self, mocker: MockerFixture) -> None:
        worker = _make_worker(mocker)
        wrapped = wrap_in_instructor_retry(_make_openai_not_found_error("Model gpt-99 not found"))
        worker.instructor_for_objects.chat.completions.create_with_completion.side_effect = wrapped  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(LLMModelNotFoundError) as exc_info:
            await worker._gen_object(llm_job=make_llm_job(mocker), schema=DummySchema)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.CONFIGURATION
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.CHANGE_MODEL
        metadata = exc_info.value.provider_metadata
        assert metadata is not None
        assert metadata.status_code == 404
        assert metadata.sdk_exception_type == "NotFoundError"

    async def test_unrecognized_underlying_falls_back_to_unknown(self, mocker: MockerFixture) -> None:
        """A wrapped non-SDK exception (e.g. validation failure) routes to UNKNOWN, not CONTENT."""
        worker = _make_worker(mocker)
        wrapped = wrap_in_instructor_retry(ValueError("Schema validation failed"))
        worker.instructor_for_objects.chat.completions.create_with_completion.side_effect = wrapped  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(LLMCompletionError) as exc_info:
            await worker._gen_object(llm_job=make_llm_job(mocker), schema=DummySchema)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.UNKNOWN
        assert exc_info.value.__cause__ is wrapped
        assert exc_info.value.provider_metadata is not None
        assert exc_info.value.provider_metadata.sdk_exception_type == "ValueError"

    async def test_real_instructor_transport_error_is_unwrapped(self, mocker: MockerFixture) -> None:
        """End-to-end: drive the real instructor library with an SDK transport exception and verify
        that instructor, confined to schema re-ask, does not retry it: it raises an ``InstructorRetryException``
        from it after the one attempt, which the worker unwraps to classify the SDK exception as TRANSIENT.
        """
        import instructor  # ruff: ignore[import-outside-top-level]  # imported here to mirror runtime usage

        worker = _make_worker(mocker)

        openai_client = openai.AsyncOpenAI(api_key="fake")
        sdk_exc = _make_openai_rate_limit_error("Rate limit exceeded — please retry")
        openai_client.chat.completions.create = mocker.AsyncMock(side_effect=sdk_exc)  # type: ignore[method-assign]
        worker.instructor_for_objects = instructor.from_openai(openai_client)

        with pytest.raises(LLMCompletionError) as exc_info:
            await worker._gen_object(llm_job=make_llm_job(mocker), schema=DummySchema)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.TRANSIENT
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.WAIT_AND_RETRY
        metadata = exc_info.value.provider_metadata
        assert metadata is not None
        assert metadata.provider == "openai"
        assert metadata.status_code == 429
        # instructor raises its InstructorRetryException from the SDK exception, which it did not retry
        wrapper_exc = exc_info.value.__cause__
        assert wrapper_exc is not None
        assert wrapper_exc.__cause__ is sdk_exc

    async def test_real_instructor_transport_error_after_a_reask_is_unwrapped(self, mocker: MockerFixture) -> None:
        """The first response fails the schema and is re-asked, then the re-ask fails in transport. The
        transport error ended the loop, so it is what the worker classifies, not the earlier parse failure
        that instructor keeps in ``failed_attempts``.
        """
        import instructor  # ruff: ignore[import-outside-top-level]  # imported here to mirror runtime usage
        from openai.types.chat import ChatCompletion  # ruff: ignore[import-outside-top-level]

        worker = _make_worker(mocker)
        off_schema_completion = ChatCompletion.model_validate(
            {
                "id": "chatcmpl-off-schema",
                "object": "chat.completion",
                "created": 0,
                "model": "gpt-4o",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "tool_calls",
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {"id": "call_1", "type": "function", "function": {"name": "DummySchema", "arguments": '{"wrong": 1}'}},
                            ],
                        },
                    }
                ],
            }
        )
        sdk_exc = _make_openai_rate_limit_error("Rate limit exceeded — please retry")
        openai_client = openai.AsyncOpenAI(api_key="fake")
        create = mocker.AsyncMock(side_effect=[off_schema_completion, sdk_exc])
        openai_client.chat.completions.create = create  # type: ignore[method-assign]
        worker.instructor_for_objects = instructor.from_openai(openai_client)
        llm_job = make_llm_job(mocker)
        llm_job.job_config.schema_reask_max_attempts = 3

        with pytest.raises(LLMCompletionError) as exc_info:
            await worker._gen_object(llm_job=llm_job, schema=DummySchema)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert create.call_count == 2
        assert exc_info.value.error_category is InferenceErrorCategory.TRANSIENT
        metadata = exc_info.value.provider_metadata
        assert metadata is not None
        assert metadata.status_code == 429
        assert metadata.sdk_exception_type == "RateLimitError"

    @pytest.mark.parametrize(
        ("sdk_exc", "expected_category"),
        [
            (_make_openai_connection_error(), InferenceErrorCategory.TRANSIENT),
            (_make_openai_timeout_error(), InferenceErrorCategory.TRANSIENT),
            (_make_openai_rate_limit_error("Rate limit exceeded — please retry"), InferenceErrorCategory.TRANSIENT),
        ],
    )
    async def test_raw_sdk_transport_error_is_classified(
        self,
        mocker: MockerFixture,
        sdk_exc: Exception,
        expected_category: InferenceErrorCategory,
    ) -> None:
        """W2.3 regression: a raw SDK transport exception reaching the worker unwrapped, as it would if
        ``instructor`` stopped wrapping the exception that ends its loop, must be classified into the
        right category, never flattened to ``UNKNOWN``, never escape unhandled.
        """
        worker = _make_worker(mocker)
        worker.instructor_for_objects.chat.completions.create_with_completion.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(LLMCompletionError) as exc_info:
            await worker._gen_object(llm_job=make_llm_job(mocker), schema=DummySchema)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is expected_category
        assert exc_info.value.__cause__ is sdk_exc
