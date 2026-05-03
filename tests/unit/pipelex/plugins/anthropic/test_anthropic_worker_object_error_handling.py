"""Tests for Anthropic worker structured-generation error handling.

Verifies that ``_gen_object`` correctly unwraps ``InstructorRetryException`` to
recover the underlying Anthropic SDK exception so transient/capacity/auth errors
are categorized correctly instead of being flattened to ``CONTENT``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import anthropic
import httpx
import pytest
from instructor.core import FailedAttempt, InstructorRetryException
from pydantic import BaseModel
from tenacity import RetryError

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

from pipelex.cogt.exceptions import InferenceErrorCategory, LLMCompletionError
from pipelex.plugins.anthropic.anthropic_exceptions import AnthropicCredentialsError
from pipelex.plugins.anthropic.anthropic_llm_worker import AnthropicLLMWorker


def _mock_httpx_response(status_code: int) -> httpx.Response:
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    return httpx.Response(status_code=status_code, request=request)


def _make_anthropic_rate_limit_error(message: str) -> anthropic.RateLimitError:
    return anthropic.RateLimitError(message, response=_mock_httpx_response(429), body=None)


def _make_anthropic_bad_request_error(message: str) -> anthropic.BadRequestError:
    return anthropic.BadRequestError(message, response=_mock_httpx_response(400), body=None)


def _make_anthropic_timeout_error() -> anthropic.APITimeoutError:
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    return anthropic.APITimeoutError(request=request)


def _make_anthropic_connection_error(message: str = "Connection refused") -> anthropic.APIConnectionError:
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    return anthropic.APIConnectionError(message=message, request=request)


def _make_anthropic_auth_error(message: str) -> anthropic.AuthenticationError:
    return anthropic.AuthenticationError(message, response=_mock_httpx_response(401), body=None)


def _make_anthropic_permission_denied_error(message: str) -> anthropic.PermissionDeniedError:
    return anthropic.PermissionDeniedError(message, response=_mock_httpx_response(403), body=None)


def _wrap_in_instructor_retry(sdk_exc: Exception, *, include_failed_attempts: bool = True) -> InstructorRetryException:
    """Build an ``InstructorRetryException`` as instructor's retry loop would."""
    failed_attempts: list[FailedAttempt] | None = [FailedAttempt(attempt_number=1, exception=sdk_exc)] if include_failed_attempts else None
    return InstructorRetryException(
        str(sdk_exc),
        last_completion=None,
        n_attempts=1,
        total_usage=0,
        create_kwargs={},
        failed_attempts=failed_attempts,
    )


class _DummySchema(BaseModel):
    value: str


def _make_worker(mocker: MockerFixture) -> AnthropicLLMWorker:
    worker = object.__new__(AnthropicLLMWorker)
    mock_model = mocker.MagicMock()
    mock_model.desc = "test-model-desc"
    mock_model.model_id = "claude-sonnet-4-20250514"
    mock_model.name = "claude-sonnet-4"
    mock_model.thinking_mode = None
    mock_model.max_tokens = 4096
    # listed_constraints is a list; the worker checks `in`, so an empty list is fine
    mock_model.listed_constraints = []
    worker.inference_model = mock_model
    worker.default_max_tokens = 4096

    instructor_client = mocker.MagicMock()
    instructor_client.chat.completions.create_with_completion = mocker.AsyncMock()
    worker.instructor_for_objects = instructor_client

    return worker


def _make_llm_job(mocker: MockerFixture) -> Any:
    job = mocker.MagicMock()
    job.applied_job_params = None
    job.job_params.temperature = 0.5
    job.job_params.max_tokens = None
    job.job_params.reasoning_effort = None
    job.job_params.reasoning_budget = None
    job.job_config.max_retries = 1
    job.job_report.llm_tokens_usage = None
    return job


def _patch_gen_object_dependencies(mocker: MockerFixture) -> None:
    """Patch the module-level helpers _gen_object relies on."""
    config_mock = mocker.MagicMock()
    config_mock.cogt.llm_config.anthropic_config.structured_output_timeout_seconds = 1200
    mocker.patch("pipelex.plugins.anthropic.anthropic_llm_worker.get_config", return_value=config_mock)
    mocker.patch(
        "pipelex.plugins.anthropic.anthropic_llm_worker.AnthropicFactory.make_simple_messages",
        new=mocker.AsyncMock(return_value=[]),
    )
    mocker.patch(
        "pipelex.plugins.anthropic.anthropic_llm_worker.AnthropicFactory.calculate_safe_max_tokens_for_timeout",
        return_value=4096,
    )


@pytest.mark.asyncio(loop_scope="class")
class TestAnthropicWorkerObjectErrorHandling:
    """``_gen_object`` must categorize SDK errors that ``instructor`` wraps in ``InstructorRetryException``."""

    async def test_wrapped_rate_limit_is_transient(self, mocker: MockerFixture) -> None:
        _patch_gen_object_dependencies(mocker)
        worker = _make_worker(mocker)
        sdk_exc = _make_anthropic_rate_limit_error("Number of request tokens has exceeded your per-minute limit")
        wrapped = _wrap_in_instructor_retry(sdk_exc)
        worker.instructor_for_objects.chat.completions.create_with_completion.side_effect = wrapped  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(LLMCompletionError) as exc_info:
            await worker._gen_object(llm_job=_make_llm_job(mocker), schema=_DummySchema)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.TRANSIENT
        assert exc_info.value.user_action is not None
        assert "retry" in exc_info.value.user_action.lower()
        assert exc_info.value.__cause__ is wrapped

    async def test_wrapped_rate_limit_quota_is_capacity(self, mocker: MockerFixture) -> None:
        _patch_gen_object_dependencies(mocker)
        worker = _make_worker(mocker)
        sdk_exc = _make_anthropic_rate_limit_error("Your account quota has been exceeded")
        wrapped = _wrap_in_instructor_retry(sdk_exc)
        worker.instructor_for_objects.chat.completions.create_with_completion.side_effect = wrapped  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(LLMCompletionError) as exc_info:
            await worker._gen_object(llm_job=_make_llm_job(mocker), schema=_DummySchema)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.CAPACITY
        assert exc_info.value.user_action is not None
        assert "billing" in exc_info.value.user_action.lower()

    async def test_wrapped_timeout_is_transient(self, mocker: MockerFixture) -> None:
        _patch_gen_object_dependencies(mocker)
        worker = _make_worker(mocker)
        wrapped = _wrap_in_instructor_retry(_make_anthropic_timeout_error())
        worker.instructor_for_objects.chat.completions.create_with_completion.side_effect = wrapped  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(LLMCompletionError) as exc_info:
            await worker._gen_object(llm_job=_make_llm_job(mocker), schema=_DummySchema)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.TRANSIENT

    async def test_wrapped_bad_request_content_policy(self, mocker: MockerFixture) -> None:
        _patch_gen_object_dependencies(mocker)
        worker = _make_worker(mocker)
        sdk_exc = _make_anthropic_bad_request_error("Your request was rejected due to content_policy_violation")
        wrapped = _wrap_in_instructor_retry(sdk_exc)
        worker.instructor_for_objects.chat.completions.create_with_completion.side_effect = wrapped  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(LLMCompletionError) as exc_info:
            await worker._gen_object(llm_job=_make_llm_job(mocker), schema=_DummySchema)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.CONTENT
        assert exc_info.value.user_action is not None
        assert "safety filters" in exc_info.value.user_action.lower()

    async def test_wrapped_connection_error_is_transient(self, mocker: MockerFixture) -> None:
        _patch_gen_object_dependencies(mocker)
        worker = _make_worker(mocker)
        wrapped = _wrap_in_instructor_retry(_make_anthropic_connection_error())
        worker.instructor_for_objects.chat.completions.create_with_completion.side_effect = wrapped  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(LLMCompletionError) as exc_info:
            await worker._gen_object(llm_job=_make_llm_job(mocker), schema=_DummySchema)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.TRANSIENT

    async def test_wrapped_auth_error_raises_credentials_error(self, mocker: MockerFixture) -> None:
        _patch_gen_object_dependencies(mocker)
        worker = _make_worker(mocker)
        wrapped = _wrap_in_instructor_retry(_make_anthropic_auth_error("Invalid API key"))
        worker.instructor_for_objects.chat.completions.create_with_completion.side_effect = wrapped  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(AnthropicCredentialsError) as exc_info:
            await worker._gen_object(llm_job=_make_llm_job(mocker), schema=_DummySchema)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.CONFIGURATION

    async def test_wrapped_permission_quota_is_capacity(self, mocker: MockerFixture) -> None:
        _patch_gen_object_dependencies(mocker)
        worker = _make_worker(mocker)
        wrapped = _wrap_in_instructor_retry(_make_anthropic_permission_denied_error("Your account quota has been exceeded"))
        worker.instructor_for_objects.chat.completions.create_with_completion.side_effect = wrapped  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(LLMCompletionError) as exc_info:
            await worker._gen_object(llm_job=_make_llm_job(mocker), schema=_DummySchema)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.CAPACITY

    async def test_unrecognized_underlying_falls_back_to_content(self, mocker: MockerFixture) -> None:
        """A wrapped non-SDK exception (e.g. validation failure) keeps the CONTENT fallback."""
        _patch_gen_object_dependencies(mocker)
        worker = _make_worker(mocker)
        wrapped = _wrap_in_instructor_retry(ValueError("Schema validation failed"))
        worker.instructor_for_objects.chat.completions.create_with_completion.side_effect = wrapped  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(LLMCompletionError) as exc_info:
            await worker._gen_object(llm_job=_make_llm_job(mocker), schema=_DummySchema)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.CONTENT
        assert exc_info.value.__cause__ is wrapped

    async def test_extract_underlying_uses_cause_when_failed_attempts_missing(self, mocker: MockerFixture) -> None:
        """When ``failed_attempts`` is None, the helper must fall back to walking ``__cause__``."""
        sdk_exc = _make_anthropic_rate_limit_error("Rate limited")
        retry_error = RetryError(last_attempt=mocker.MagicMock(_exception=sdk_exc))
        wrapped = _wrap_in_instructor_retry(sdk_exc, include_failed_attempts=False)
        wrapped.__cause__ = retry_error

        recovered = AnthropicLLMWorker._extract_underlying_sdk_exception(instructor_exc=wrapped)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert recovered is sdk_exc

    async def test_real_instructor_wraps_rate_limit_and_fix_unwraps_correctly(self, mocker: MockerFixture) -> None:
        """End-to-end: drive the real instructor library with an SDK exception and
        verify the worker still categorizes it as TRANSIENT.

        This locks in two assumptions our unit tests rely on:
        1. instructor really does wrap ``RateLimitError`` in ``InstructorRetryException``
           (if a future instructor version stops doing this, the bug disappears and
           this test should be revisited).
        2. ``InstructorRetryException.failed_attempts[-1].exception`` is the original
           SDK exception, so our extractor recovers the right object.
        """
        import instructor  # noqa: PLC0415  # imported here to mirror runtime usage

        _patch_gen_object_dependencies(mocker)
        worker = _make_worker(mocker)

        anthropic_client = anthropic.AsyncAnthropic(api_key="fake")
        sdk_exc = _make_anthropic_rate_limit_error("Number of request tokens has exceeded your per-minute limit")
        anthropic_client.messages.create = mocker.AsyncMock(side_effect=sdk_exc)  # type: ignore[method-assign]
        worker.instructor_for_objects = instructor.from_anthropic(anthropic_client)

        with pytest.raises(LLMCompletionError) as exc_info:
            await worker._gen_object(llm_job=_make_llm_job(mocker), schema=_DummySchema)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.TRANSIENT
        # The ``from`` chain should preserve the wrapper (not the raw SDK exc),
        # so traceback shows the full instructor → tenacity → SDK story.
        cause = exc_info.value.__cause__
        assert isinstance(cause, InstructorRetryException)
        assert cause.failed_attempts is not None
        assert isinstance(cause.failed_attempts[-1].exception, anthropic.RateLimitError)
