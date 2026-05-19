"""Tests for Mistral LLM worker structured-generation error handling.

Verifies that ``_gen_object`` correctly unwraps ``InstructorRetryException`` to
recover the underlying ``MistralError``, attaches ``ProviderErrorMetadata``,
and surfaces semantic ``UserActionKind`` values — so transient/capacity/auth
errors are categorized correctly instead of being flattened to ``CONTENT``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx
import pytest
from mistralai import Mistral, MistralError

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

from pipelex.cogt.exceptions import InferenceErrorCategory, LLMCompletionError, LLMModelNotFoundError
from pipelex.cogt.inference.error_classification import UserActionKind
from pipelex.plugins.mistral.mistral_llm_worker import MistralLLMWorker
from tests.helpers.instructor_test_utils import DummySchema, make_llm_job, wrap_in_instructor_retry


def _mock_httpx_response(status_code: int, headers: dict[str, str] | None = None, text: str = "") -> httpx.Response:
    request = httpx.Request("POST", "https://api.mistral.ai/v1/chat/completions")
    return httpx.Response(status_code=status_code, request=request, headers=headers or {}, text=text)


def _make_mistral_error(
    status_code: int,
    message: str,
    *,
    headers: dict[str, str] | None = None,
    body_text: str = "",
) -> MistralError:
    return MistralError(message, raw_response=_mock_httpx_response(status_code, headers=headers, text=body_text))


def _make_worker(mocker: MockerFixture) -> MistralLLMWorker:
    worker = object.__new__(MistralLLMWorker)
    mock_model = mocker.MagicMock()
    mock_model.desc = "test-model-desc"
    mock_model.model_id = "mistral-large"
    mock_model.name = "mistral-large"
    mock_model.thinking_mode = None
    mock_model.max_tokens = 4096
    worker.inference_model = mock_model
    worker.default_max_tokens = 4096

    instructor_client = mocker.MagicMock()
    instructor_client.chat.completions.create_with_completion = mocker.AsyncMock()
    worker.instructor_for_objects = instructor_client

    mock_factory = mocker.MagicMock()
    mock_factory.make_simple_messages_openai_typed = mocker.AsyncMock(return_value=[])
    worker.mistral_factory = mock_factory

    return worker


@pytest.mark.asyncio(loop_scope="class")
class TestMistralLLMWorkerObjectErrorHandling:
    """``_gen_object`` must categorize ``MistralError`` instances wrapped in ``InstructorRetryException``."""

    async def test_wrapped_rate_limit_generic_is_transient(self, mocker: MockerFixture) -> None:
        worker = _make_worker(mocker)
        sdk_exc = _make_mistral_error(
            429,
            "Rate limit exceeded. Please retry after 20s",
            headers={"x-request-id": "req_rate", "retry-after": "3"},
            body_text='{"message": "Rate limit", "type": "rate_limit_error", "code": "rate_limit_exceeded"}',
        )
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
        assert metadata.provider == "mistral"
        assert metadata.sdk_exception_type == "MistralError"
        assert metadata.status_code == 429
        assert metadata.request_id == "req_rate"
        assert metadata.retry_after_seconds == 3.0
        assert metadata.provider_error_code == "rate_limit_error"

    async def test_wrapped_rate_limit_quota_is_capacity(self, mocker: MockerFixture) -> None:
        worker = _make_worker(mocker)
        sdk_exc = _make_mistral_error(
            429,
            "Rate limit reached: your account quota has been exceeded",
        )
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

    async def test_wrapped_payment_required_is_capacity(self, mocker: MockerFixture) -> None:
        worker = _make_worker(mocker)
        sdk_exc = _make_mistral_error(402, "Payment required: insufficient credits")
        wrapped = wrap_in_instructor_retry(sdk_exc)
        worker.instructor_for_objects.chat.completions.create_with_completion.side_effect = wrapped  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(LLMCompletionError) as exc_info:
            await worker._gen_object(llm_job=make_llm_job(mocker), schema=DummySchema)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.CAPACITY
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.CHECK_BILLING
        metadata = exc_info.value.provider_metadata
        assert metadata is not None
        assert metadata.status_code == 402

    async def test_wrapped_bad_request_content_policy(self, mocker: MockerFixture) -> None:
        worker = _make_worker(mocker)
        sdk_exc = _make_mistral_error(400, "Your request was rejected due to content_policy_violation")
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

    async def test_wrapped_bad_request_generic_is_content(self, mocker: MockerFixture) -> None:
        worker = _make_worker(mocker)
        sdk_exc = _make_mistral_error(400, "Invalid parameter: temperature must be between 0 and 1")
        wrapped = wrap_in_instructor_retry(sdk_exc)
        worker.instructor_for_objects.chat.completions.create_with_completion.side_effect = wrapped  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(LLMCompletionError) as exc_info:
            await worker._gen_object(llm_job=make_llm_job(mocker), schema=DummySchema)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.CONTENT
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.CHANGE_INPUT
        metadata = exc_info.value.provider_metadata
        assert metadata is not None
        assert metadata.status_code == 400

    async def test_wrapped_auth_error_is_configuration(self, mocker: MockerFixture) -> None:
        worker = _make_worker(mocker)
        sdk_exc = _make_mistral_error(401, "Invalid API key provided")
        wrapped = wrap_in_instructor_retry(sdk_exc)
        worker.instructor_for_objects.chat.completions.create_with_completion.side_effect = wrapped  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(LLMCompletionError) as exc_info:
            await worker._gen_object(llm_job=make_llm_job(mocker), schema=DummySchema)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.CONFIGURATION
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.CHECK_CREDENTIALS
        metadata = exc_info.value.provider_metadata
        assert metadata is not None
        assert metadata.status_code == 401

    async def test_wrapped_not_found_raises_llm_model_not_found_error(self, mocker: MockerFixture) -> None:
        worker = _make_worker(mocker)
        sdk_exc = _make_mistral_error(404, "Model mistral-unknown not found")
        wrapped = wrap_in_instructor_retry(sdk_exc)
        worker.instructor_for_objects.chat.completions.create_with_completion.side_effect = wrapped  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(LLMModelNotFoundError) as exc_info:
            await worker._gen_object(llm_job=make_llm_job(mocker), schema=DummySchema)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.CONFIGURATION
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.CHANGE_MODEL
        metadata = exc_info.value.provider_metadata
        assert metadata is not None
        assert metadata.status_code == 404

    async def test_wrapped_server_error_is_transient(self, mocker: MockerFixture) -> None:
        worker = _make_worker(mocker)
        sdk_exc = _make_mistral_error(500, "Internal server error")
        wrapped = wrap_in_instructor_retry(sdk_exc)
        worker.instructor_for_objects.chat.completions.create_with_completion.side_effect = wrapped  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(LLMCompletionError) as exc_info:
            await worker._gen_object(llm_job=make_llm_job(mocker), schema=DummySchema)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.TRANSIENT
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.WAIT_AND_RETRY
        metadata = exc_info.value.provider_metadata
        assert metadata is not None
        assert metadata.status_code == 500

    async def test_unrecognized_underlying_falls_back_to_unknown(self, mocker: MockerFixture) -> None:
        """A wrapped non-MistralError exception (e.g. schema validation) routes to UNKNOWN, not CONTENT."""
        worker = _make_worker(mocker)
        wrapped = wrap_in_instructor_retry(ValueError("Schema validation failed"))
        worker.instructor_for_objects.chat.completions.create_with_completion.side_effect = wrapped  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(LLMCompletionError) as exc_info:
            await worker._gen_object(llm_job=make_llm_job(mocker), schema=DummySchema)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.UNKNOWN
        assert exc_info.value.__cause__ is wrapped
        assert exc_info.value.provider_metadata is None
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.CONTACT_SUPPORT

    async def test_real_instructor_propagates_transport_error_raw(self, mocker: MockerFixture) -> None:
        """End-to-end: drive the real instructor library with a ``MistralError`` and verify the
        W2.3 behavior — instructor, confined to schema re-ask, does NOT retry the transport error
        and does NOT wrap it in ``InstructorRetryException``. It propagates as the raw
        ``MistralError``, which the worker classifies as TRANSIENT with provider metadata.
        """
        import instructor  # noqa: PLC0415

        worker = _make_worker(mocker)

        mistral_client = Mistral(api_key="fake")
        sdk_exc = _make_mistral_error(429, "Rate limit exceeded. Please retry after 20s")
        mistral_client.chat.complete_async = mocker.AsyncMock(side_effect=sdk_exc)  # type: ignore[method-assign]  # pyright: ignore[reportAttributeAccessIssue]
        worker.instructor_for_objects = instructor.from_mistral(client=mistral_client, use_async=True)

        with pytest.raises(LLMCompletionError) as exc_info:
            await worker._gen_object(llm_job=make_llm_job(mocker), schema=DummySchema)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.TRANSIENT
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.WAIT_AND_RETRY
        metadata = exc_info.value.provider_metadata
        assert metadata is not None
        assert metadata.provider == "mistral"
        assert metadata.status_code == 429
        # The raw SDK exception propagates and chains directly — instructor no longer wraps it.
        assert exc_info.value.__cause__ is sdk_exc

    @pytest.mark.parametrize(
        ("sdk_exc", "expected_category"),
        [
            (_make_mistral_error(500, "Internal server error"), InferenceErrorCategory.TRANSIENT),
            (_make_mistral_error(429, "Rate limit exceeded. Please retry after 20s"), InferenceErrorCategory.TRANSIENT),
            (httpx.ConnectError("Connection refused"), InferenceErrorCategory.TRANSIENT),
            (httpx.ReadTimeout("Read timed out"), InferenceErrorCategory.TRANSIENT),
        ],
    )
    async def test_raw_sdk_transport_error_is_classified(
        self,
        mocker: MockerFixture,
        sdk_exc: Exception,
        expected_category: InferenceErrorCategory,
    ) -> None:
        """W2.3 regression: a raw ``MistralError`` / ``httpx`` transport exception from
        ``create_with_completion`` is classified, never flattened to ``UNKNOWN``. The ``httpx``
        cases cover the Mistral SDK's habit of letting raw connection / timeout errors propagate
        outside the ``MistralError`` hierarchy — which the worker's added ``except`` clause catches.
        """
        worker = _make_worker(mocker)
        worker.instructor_for_objects.chat.completions.create_with_completion.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(LLMCompletionError) as exc_info:
            await worker._gen_object(llm_job=make_llm_job(mocker), schema=DummySchema)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is expected_category
        assert exc_info.value.__cause__ is sdk_exc
