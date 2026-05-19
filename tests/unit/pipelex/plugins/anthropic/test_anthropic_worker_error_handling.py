"""Tests for Anthropic worker SDK exception handling and error categorization."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import anthropic
import httpx
import pytest

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

from pipelex.cogt.exceptions import InferenceErrorCategory, LLMCompletionError, LLMModelNotFoundError
from pipelex.plugins.anthropic.anthropic_exceptions import AnthropicCredentialsError
from pipelex.plugins.anthropic.anthropic_llm_worker import AnthropicLLMWorker
from tests.unit.pipelex.plugins.anthropic.test_data import AnthropicErrorHandlingTestData


def _mock_httpx_response(status_code: int = 429) -> httpx.Response:
    """Create a minimal httpx.Response for constructing SDK exceptions."""
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    return httpx.Response(status_code=status_code, request=request)


def _make_anthropic_rate_limit_error(message: str) -> anthropic.RateLimitError:
    return anthropic.RateLimitError(message, response=_mock_httpx_response(429), body=None)


def _make_anthropic_bad_request_error(message: str) -> anthropic.BadRequestError:
    return anthropic.BadRequestError(message, response=_mock_httpx_response(400), body=None)


def _make_anthropic_timeout_error() -> anthropic.APITimeoutError:
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    return anthropic.APITimeoutError(request=request)


def _make_anthropic_connection_error(message: str = "Connection error.") -> anthropic.APIConnectionError:
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    return anthropic.APIConnectionError(message=message, request=request)


def _make_anthropic_auth_error(message: str) -> anthropic.AuthenticationError:
    return anthropic.AuthenticationError(message, response=_mock_httpx_response(401), body=None)


def _make_anthropic_permission_denied_error(message: str) -> anthropic.PermissionDeniedError:
    return anthropic.PermissionDeniedError(message, response=_mock_httpx_response(403), body=None)


def _make_anthropic_internal_server_error(message: str) -> anthropic.InternalServerError:
    return anthropic.InternalServerError(message, response=_mock_httpx_response(500), body=None)


def _make_anthropic_conflict_error(message: str) -> anthropic.ConflictError:
    return anthropic.ConflictError(message, response=_mock_httpx_response(409), body=None)


def _make_anthropic_not_found_error(message: str) -> anthropic.NotFoundError:
    return anthropic.NotFoundError(message, response=_mock_httpx_response(404), body=None)


def _make_worker(mocker: MockerFixture) -> AnthropicLLMWorker:
    """Create a minimal AnthropicLLMWorker with mocked internals."""
    worker = object.__new__(AnthropicLLMWorker)
    mock_model = mocker.MagicMock()
    mock_model.desc = "test-model-desc"
    mock_model.model_id = "claude-sonnet-4-20250514"
    mock_model.name = "claude-sonnet-4"
    mock_model.thinking_mode = None
    mock_model.max_tokens = 4096
    worker.inference_model = mock_model
    worker.default_max_tokens = 4096

    # Mock the streaming client
    mock_client = mocker.MagicMock()
    mock_stream_context = mocker.MagicMock()
    mock_stream_context.__aenter__ = mocker.AsyncMock()
    mock_stream_context.__aexit__ = mocker.AsyncMock(return_value=False)
    mock_client.messages.stream = mocker.MagicMock(return_value=mock_stream_context)
    worker.anthropic_async_client = mock_client

    return worker


def _make_llm_job(mocker: MockerFixture) -> Any:
    """Create a mock LLM job."""
    job = mocker.MagicMock()
    job.applied_job_params = None
    job.job_params.temperature = 0.5
    job.job_params.max_tokens = None
    job.job_params.reasoning_effort = None
    job.job_params.reasoning_budget = None
    job.job_report.llm_tokens_usage = None
    job.llm_prompt.system_text = "system"
    return job


@pytest.mark.asyncio(loop_scope="class")
class TestAnthropicWorkerErrorHandling:
    """Tests for Anthropic worker SDK exception handling and error categorization."""

    # ---- RateLimitError tests ----

    @pytest.mark.parametrize(
        ("_topic", "error_message", "expected_category", "expected_action_substring"),
        AnthropicErrorHandlingTestData.RATE_LIMIT_CASES,
    )
    async def test_rate_limit(
        self,
        mocker: MockerFixture,
        _topic: str,
        error_message: str,
        expected_category: InferenceErrorCategory,
        expected_action_substring: str | None,
    ) -> None:
        """RateLimitError is caught and categorized correctly (TRANSIENT or CAPACITY)."""
        worker = _make_worker(mocker)
        sdk_exc = _make_anthropic_rate_limit_error(error_message)
        worker.anthropic_async_client.messages.stream.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(LLMCompletionError) as exc_info:
            await worker._gen_text(llm_job=_make_llm_job(mocker))  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is expected_category
        assert exc_info.value.__cause__ is sdk_exc
        if expected_action_substring:
            assert exc_info.value.user_action is not None
            assert expected_action_substring in exc_info.value.user_action.detail.lower()

    # ---- APITimeoutError test ----

    async def test_timeout_is_transient(self, mocker: MockerFixture) -> None:
        """APITimeoutError is caught and categorized as TRANSIENT."""
        worker = _make_worker(mocker)
        sdk_exc = _make_anthropic_timeout_error()
        worker.anthropic_async_client.messages.stream.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(LLMCompletionError) as exc_info:
            await worker._gen_text(llm_job=_make_llm_job(mocker))  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.TRANSIENT
        assert exc_info.value.__cause__ is sdk_exc

    # ---- BadRequestError tests with content policy detection ----

    @pytest.mark.parametrize(
        ("_topic", "error_message", "expected_category", "expected_action_substring"),
        AnthropicErrorHandlingTestData.BAD_REQUEST_CASES,
    )
    async def test_bad_request(
        self,
        mocker: MockerFixture,
        _topic: str,
        error_message: str,
        expected_category: InferenceErrorCategory,
        expected_action_substring: str | None,
    ) -> None:
        """BadRequestError is caught with content policy detection."""
        worker = _make_worker(mocker)
        sdk_exc = _make_anthropic_bad_request_error(error_message)
        worker.anthropic_async_client.messages.stream.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(LLMCompletionError) as exc_info:
            await worker._gen_text(llm_job=_make_llm_job(mocker))  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is expected_category
        assert exc_info.value.__cause__ is sdk_exc
        if expected_action_substring:
            assert exc_info.value.user_action is not None
            assert expected_action_substring in exc_info.value.user_action.detail.lower()

    # ---- Existing exception categories ----

    async def test_connection_error_is_transient(self, mocker: MockerFixture) -> None:
        """APIConnectionError should be categorized as TRANSIENT."""
        worker = _make_worker(mocker)
        sdk_exc = _make_anthropic_connection_error("Connection refused")
        worker.anthropic_async_client.messages.stream.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(LLMCompletionError) as exc_info:
            await worker._gen_text(llm_job=_make_llm_job(mocker))  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.TRANSIENT
        assert exc_info.value.__cause__ is sdk_exc

    async def test_auth_error_is_configuration(self, mocker: MockerFixture) -> None:
        """AuthenticationError raises AnthropicCredentialsError with CONFIGURATION category."""
        worker = _make_worker(mocker)
        sdk_exc = _make_anthropic_auth_error("Invalid API key")
        worker.anthropic_async_client.messages.stream.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(AnthropicCredentialsError) as exc_info:
            await worker._gen_text(llm_job=_make_llm_job(mocker))  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.CONFIGURATION
        assert exc_info.value.__cause__ is sdk_exc

    # ---- PermissionDeniedError tests ----

    async def test_permission_denied_quota_is_capacity(self, mocker: MockerFixture) -> None:
        """PermissionDeniedError with quota message is CAPACITY."""
        worker = _make_worker(mocker)
        sdk_exc = _make_anthropic_permission_denied_error("Your account quota has been exceeded")
        worker.anthropic_async_client.messages.stream.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(LLMCompletionError) as exc_info:
            await worker._gen_text(llm_job=_make_llm_job(mocker))  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.CAPACITY

    async def test_permission_denied_generic_is_configuration(self, mocker: MockerFixture) -> None:
        """PermissionDeniedError without quota message is CONFIGURATION."""
        worker = _make_worker(mocker)
        sdk_exc = _make_anthropic_permission_denied_error("You do not have access to this resource")
        worker.anthropic_async_client.messages.stream.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(LLMCompletionError) as exc_info:
            await worker._gen_text(llm_job=_make_llm_job(mocker))  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.CONFIGURATION

    # ---- Generic APIStatusError fallback ----

    async def test_server_error_is_transient(self, mocker: MockerFixture) -> None:
        """A 5xx APIStatusError is caught and categorized TRANSIENT via the generic fallback."""
        worker = _make_worker(mocker)
        sdk_exc = _make_anthropic_internal_server_error("Internal server error")
        worker.anthropic_async_client.messages.stream.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(LLMCompletionError) as exc_info:
            await worker._gen_text(llm_job=_make_llm_job(mocker))  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.TRANSIENT
        assert exc_info.value.__cause__ is sdk_exc
        metadata = exc_info.value.provider_metadata
        assert metadata is not None
        assert metadata.status_code == 500

    async def test_generic_status_error_is_configuration(self, mocker: MockerFixture) -> None:
        """An unhandled 4xx APIStatusError (e.g. 409 Conflict) is caught and categorized CONFIGURATION."""
        worker = _make_worker(mocker)
        sdk_exc = _make_anthropic_conflict_error("Conflict")
        worker.anthropic_async_client.messages.stream.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(LLMCompletionError) as exc_info:
            await worker._gen_text(llm_job=_make_llm_job(mocker))  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.CONFIGURATION
        assert exc_info.value.__cause__ is sdk_exc
        metadata = exc_info.value.provider_metadata
        assert metadata is not None
        assert metadata.status_code == 409

    # ---- NotFoundError specialization ----

    async def test_not_found_raises_llm_model_not_found_error(self, mocker: MockerFixture) -> None:
        """A 404 NotFoundError specializes to LLMModelNotFoundError (CONFIGURATION) carrying the model handle."""
        worker = _make_worker(mocker)
        sdk_exc = _make_anthropic_not_found_error("Model claude-99 not found")
        worker.anthropic_async_client.messages.stream.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(LLMModelNotFoundError) as exc_info:
            await worker._gen_text(llm_job=_make_llm_job(mocker))  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.CONFIGURATION
        assert exc_info.value.model_handle == "claude-sonnet-4"
        assert exc_info.value.__cause__ is sdk_exc

    # ---- to_error_report() integration ----

    async def test_error_report_includes_category(self, mocker: MockerFixture) -> None:
        """to_error_report() includes error_category and retryable from the exception."""
        worker = _make_worker(mocker)
        sdk_exc = _make_anthropic_rate_limit_error("Rate limit exceeded")
        worker.anthropic_async_client.messages.stream.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(LLMCompletionError) as exc_info:
            await worker._gen_text(llm_job=_make_llm_job(mocker))  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        report = exc_info.value.to_error_report()
        assert report.error_category == "transient"
        assert report.retryable is True
