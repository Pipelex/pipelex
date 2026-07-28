"""Tests for Anthropic worker structured-generation error handling.

Verifies that ``_gen_object`` correctly unwraps ``InstructorRetryException`` to
recover the underlying Anthropic SDK exception so transient/capacity/auth errors
are categorized correctly instead of being flattened to ``CONTENT``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import anthropic
import httpx
import pytest

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

from pipelex.cogt.exceptions import InferenceErrorCategory, LLMCompletionError, LLMModelNotFoundError
from pipelex.cogt.inference.error_classification import UserActionKind
from pipelex.providers.anthropic.anthropic_llm_worker import AnthropicLLMWorker
from tests.helpers.instructor_test_utils import DummySchema, make_llm_job, wrap_in_instructor_retry


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


def _make_anthropic_internal_server_error(message: str) -> anthropic.InternalServerError:
    return anthropic.InternalServerError(message, response=_mock_httpx_response(500), body=None)


def _make_anthropic_conflict_error(message: str) -> anthropic.ConflictError:
    return anthropic.ConflictError(message, response=_mock_httpx_response(409), body=None)


def _make_anthropic_not_found_error(message: str) -> anthropic.NotFoundError:
    return anthropic.NotFoundError(message, response=_mock_httpx_response(404), body=None)


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


def _patch_gen_object_dependencies(mocker: MockerFixture) -> None:
    """Patch the module-level helpers _gen_object relies on."""
    config_mock = mocker.MagicMock()
    config_mock.cogt.llm_config.anthropic_config.structured_output_timeout_seconds = 1200
    mocker.patch("pipelex.providers.anthropic.anthropic_llm_worker.get_config", return_value=config_mock)
    mocker.patch(
        "pipelex.providers.anthropic.anthropic_llm_worker.AnthropicFactory.make_simple_messages",
        new=mocker.AsyncMock(return_value=[]),
    )
    mocker.patch(
        "pipelex.providers.anthropic.anthropic_llm_worker.AnthropicFactory.calculate_safe_max_tokens_for_timeout",
        return_value=4096,
    )


@pytest.mark.asyncio(loop_scope="class")
class TestAnthropicWorkerObjectErrorHandling:
    """``_gen_object`` must categorize SDK errors that ``instructor`` wraps in ``InstructorRetryException``."""

    async def test_wrapped_rate_limit_is_transient(self, mocker: MockerFixture) -> None:
        _patch_gen_object_dependencies(mocker)
        worker = _make_worker(mocker)
        sdk_exc = _make_anthropic_rate_limit_error("Number of request tokens has exceeded your per-minute limit")
        wrapped = wrap_in_instructor_retry(sdk_exc)
        worker.instructor_for_objects.chat.completions.create_with_completion.side_effect = wrapped  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(LLMCompletionError) as exc_info:
            await worker._gen_object(llm_job=make_llm_job(mocker), schema=DummySchema)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.TRANSIENT
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.WAIT_AND_RETRY
        assert "retry" in exc_info.value.user_action.detail.lower()
        assert exc_info.value.__cause__ is wrapped
        metadata = exc_info.value.provider_metadata
        assert metadata is not None
        assert metadata.provider == "anthropic"
        assert metadata.sdk_exception_type == "RateLimitError"
        assert metadata.status_code == 429

    async def test_wrapped_rate_limit_quota_is_capacity(self, mocker: MockerFixture) -> None:
        _patch_gen_object_dependencies(mocker)
        worker = _make_worker(mocker)
        sdk_exc = _make_anthropic_rate_limit_error("Your account quota has been exceeded")
        wrapped = wrap_in_instructor_retry(sdk_exc)
        worker.instructor_for_objects.chat.completions.create_with_completion.side_effect = wrapped  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(LLMCompletionError) as exc_info:
            await worker._gen_object(llm_job=make_llm_job(mocker), schema=DummySchema)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.CAPACITY
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.CHECK_BILLING
        assert "billing" in exc_info.value.user_action.detail.lower()
        metadata = exc_info.value.provider_metadata
        assert metadata is not None
        assert metadata.status_code == 429
        assert metadata.sdk_exception_type == "RateLimitError"

    async def test_wrapped_timeout_is_transient(self, mocker: MockerFixture) -> None:
        _patch_gen_object_dependencies(mocker)
        worker = _make_worker(mocker)
        wrapped = wrap_in_instructor_retry(_make_anthropic_timeout_error())
        worker.instructor_for_objects.chat.completions.create_with_completion.side_effect = wrapped  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(LLMCompletionError) as exc_info:
            await worker._gen_object(llm_job=make_llm_job(mocker), schema=DummySchema)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.TRANSIENT

    async def test_wrapped_bad_request_content_policy(self, mocker: MockerFixture) -> None:
        _patch_gen_object_dependencies(mocker)
        worker = _make_worker(mocker)
        sdk_exc = _make_anthropic_bad_request_error("Your request was rejected due to content_policy_violation")
        wrapped = wrap_in_instructor_retry(sdk_exc)
        worker.instructor_for_objects.chat.completions.create_with_completion.side_effect = wrapped  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(LLMCompletionError) as exc_info:
            await worker._gen_object(llm_job=make_llm_job(mocker), schema=DummySchema)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.CONTENT
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.CHANGE_INPUT
        assert "safety filters" in exc_info.value.user_action.detail.lower()
        metadata = exc_info.value.provider_metadata
        assert metadata is not None
        assert metadata.status_code == 400
        assert metadata.sdk_exception_type == "BadRequestError"

    async def test_wrapped_connection_error_is_transient(self, mocker: MockerFixture) -> None:
        _patch_gen_object_dependencies(mocker)
        worker = _make_worker(mocker)
        wrapped = wrap_in_instructor_retry(_make_anthropic_connection_error())
        worker.instructor_for_objects.chat.completions.create_with_completion.side_effect = wrapped  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(LLMCompletionError) as exc_info:
            await worker._gen_object(llm_job=make_llm_job(mocker), schema=DummySchema)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.TRANSIENT

    async def test_wrapped_auth_error_is_configuration(self, mocker: MockerFixture) -> None:
        _patch_gen_object_dependencies(mocker)
        worker = _make_worker(mocker)
        wrapped = wrap_in_instructor_retry(_make_anthropic_auth_error("Invalid API key"))
        worker.instructor_for_objects.chat.completions.create_with_completion.side_effect = wrapped  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(LLMCompletionError) as exc_info:
            await worker._gen_object(llm_job=make_llm_job(mocker), schema=DummySchema)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.CONFIGURATION
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.CHECK_CREDENTIALS

    async def test_wrapped_permission_quota_is_capacity(self, mocker: MockerFixture) -> None:
        _patch_gen_object_dependencies(mocker)
        worker = _make_worker(mocker)
        wrapped = wrap_in_instructor_retry(_make_anthropic_permission_denied_error("Your account quota has been exceeded"))
        worker.instructor_for_objects.chat.completions.create_with_completion.side_effect = wrapped  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(LLMCompletionError) as exc_info:
            await worker._gen_object(llm_job=make_llm_job(mocker), schema=DummySchema)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.CAPACITY
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.CHECK_BILLING

    async def test_wrapped_server_error_is_transient(self, mocker: MockerFixture) -> None:
        """A wrapped 5xx APIStatusError is categorized TRANSIENT via the generic fallback branch."""
        _patch_gen_object_dependencies(mocker)
        worker = _make_worker(mocker)
        wrapped = wrap_in_instructor_retry(_make_anthropic_internal_server_error("Internal server error"))
        worker.instructor_for_objects.chat.completions.create_with_completion.side_effect = wrapped  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(LLMCompletionError) as exc_info:
            await worker._gen_object(llm_job=make_llm_job(mocker), schema=DummySchema)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.TRANSIENT
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.WAIT_AND_RETRY
        metadata = exc_info.value.provider_metadata
        assert metadata is not None
        assert metadata.status_code == 500
        assert metadata.sdk_exception_type == "InternalServerError"

    async def test_wrapped_generic_status_error_is_configuration(self, mocker: MockerFixture) -> None:
        """A wrapped unhandled 4xx APIStatusError (e.g. 409 Conflict) is categorized CONFIGURATION."""
        _patch_gen_object_dependencies(mocker)
        worker = _make_worker(mocker)
        wrapped = wrap_in_instructor_retry(_make_anthropic_conflict_error("Conflict"))
        worker.instructor_for_objects.chat.completions.create_with_completion.side_effect = wrapped  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(LLMCompletionError) as exc_info:
            await worker._gen_object(llm_job=make_llm_job(mocker), schema=DummySchema)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.CONFIGURATION
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.CHANGE_INPUT
        metadata = exc_info.value.provider_metadata
        assert metadata is not None
        assert metadata.status_code == 409
        assert metadata.sdk_exception_type == "ConflictError"

    async def test_wrapped_not_found_raises_llm_model_not_found_error(self, mocker: MockerFixture) -> None:
        """A wrapped 404 NotFoundError specializes to LLMModelNotFoundError (CONFIGURATION)."""
        _patch_gen_object_dependencies(mocker)
        worker = _make_worker(mocker)
        wrapped = wrap_in_instructor_retry(_make_anthropic_not_found_error("Model claude-99 not found"))
        worker.instructor_for_objects.chat.completions.create_with_completion.side_effect = wrapped  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(LLMModelNotFoundError) as exc_info:
            await worker._gen_object(llm_job=make_llm_job(mocker), schema=DummySchema)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.CONFIGURATION
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.CHANGE_MODEL
        assert exc_info.value.model_handle == "claude-sonnet-4"
        metadata = exc_info.value.provider_metadata
        assert metadata is not None
        assert metadata.status_code == 404
        assert metadata.sdk_exception_type == "NotFoundError"

    async def test_unrecognized_underlying_falls_back_to_unknown(self, mocker: MockerFixture) -> None:
        """A wrapped non-SDK exception (e.g. validation failure) routes to UNKNOWN, not CONTENT."""
        _patch_gen_object_dependencies(mocker)
        worker = _make_worker(mocker)
        wrapped = wrap_in_instructor_retry(ValueError("Schema validation failed"))
        worker.instructor_for_objects.chat.completions.create_with_completion.side_effect = wrapped  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(LLMCompletionError) as exc_info:
            await worker._gen_object(llm_job=make_llm_job(mocker), schema=DummySchema)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.UNKNOWN
        assert exc_info.value.__cause__ is wrapped
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.CONTACT_SUPPORT

    async def test_provider_metadata_is_serialized_in_error_report(self, mocker: MockerFixture) -> None:
        """``to_error_report()`` must surface ``provider_metadata`` so downstream consumers see it."""
        _patch_gen_object_dependencies(mocker)
        worker = _make_worker(mocker)
        sdk_exc = _make_anthropic_rate_limit_error("Your account quota has been exceeded")
        wrapped = wrap_in_instructor_retry(sdk_exc)
        worker.instructor_for_objects.chat.completions.create_with_completion.side_effect = wrapped  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(LLMCompletionError) as exc_info:
            await worker._gen_object(llm_job=make_llm_job(mocker), schema=DummySchema)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        report = exc_info.value.to_error_report()
        report_dict = report.to_dict()
        assert "provider_metadata" in report_dict
        metadata_dict = report_dict["provider_metadata"]
        assert isinstance(metadata_dict, dict)
        assert metadata_dict["provider"] == "anthropic"
        assert metadata_dict["sdk_exception_type"] == "RateLimitError"
        assert metadata_dict["status_code"] == 429
        assert "user_action" in report_dict
        user_action_dict = report_dict["user_action"]
        assert isinstance(user_action_dict, dict)
        assert user_action_dict["kind"] == UserActionKind.CHECK_BILLING
        assert isinstance(user_action_dict["detail"], str)

    async def test_real_instructor_propagates_transport_error_raw(self, mocker: MockerFixture) -> None:
        """End-to-end: drive the real instructor library with an SDK transport exception and
        verify the W2.3 behavior — instructor, confined to schema re-ask, does NOT retry the
        transport error and does NOT wrap it in ``InstructorRetryException``. It propagates as
        the raw SDK exception, which the worker's ``except`` clause classifies as TRANSIENT.
        """
        import instructor  # noqa: PLC0415  # imported here to mirror runtime usage

        _patch_gen_object_dependencies(mocker)
        worker = _make_worker(mocker)

        anthropic_client = anthropic.AsyncAnthropic(api_key="fake")
        sdk_exc = _make_anthropic_rate_limit_error("Number of request tokens has exceeded your per-minute limit")
        anthropic_client.messages.create = mocker.AsyncMock(side_effect=sdk_exc)  # type: ignore[method-assign]
        worker.instructor_for_objects = instructor.from_anthropic(anthropic_client)

        with pytest.raises(LLMCompletionError) as exc_info:
            await worker._gen_object(llm_job=make_llm_job(mocker), schema=DummySchema)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.TRANSIENT
        # The raw SDK exception propagates and chains directly — instructor no longer wraps it.
        assert exc_info.value.__cause__ is sdk_exc

    @pytest.mark.parametrize(
        ("sdk_exc", "expected_category"),
        [
            (_make_anthropic_connection_error(), InferenceErrorCategory.TRANSIENT),
            (_make_anthropic_timeout_error(), InferenceErrorCategory.TRANSIENT),
            (_make_anthropic_internal_server_error("Internal server error"), InferenceErrorCategory.TRANSIENT),
            (_make_anthropic_rate_limit_error("Number of request tokens has exceeded your per-minute limit"), InferenceErrorCategory.TRANSIENT),
        ],
    )
    async def test_raw_sdk_transport_error_is_classified(
        self,
        mocker: MockerFixture,
        sdk_exc: Exception,
        expected_category: InferenceErrorCategory,
    ) -> None:
        """W2.3 regression: now that ``instructor`` no longer retries transport errors, a raw SDK
        transport exception is the primary path out of ``create_with_completion`` — it must be
        classified into the right category, never flattened to ``UNKNOWN``, never escape unhandled.
        """
        _patch_gen_object_dependencies(mocker)
        worker = _make_worker(mocker)
        worker.instructor_for_objects.chat.completions.create_with_completion.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(LLMCompletionError) as exc_info:
            await worker._gen_object(llm_job=make_llm_job(mocker), schema=DummySchema)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is expected_category
        assert exc_info.value.__cause__ is sdk_exc
