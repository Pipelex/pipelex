"""Tests for Google LLM worker structured-generation error handling.

Verifies that ``_gen_object`` correctly unwraps ``InstructorRetryException`` to
recover the underlying ``ClientError`` / ``ServerError``, attaches
``ProviderErrorMetadata``, and surfaces semantic ``UserActionKind`` values — so
transient/capacity/auth errors aren't all flattened to ``CONTENT`` like the
pre-fix behavior.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx
import pytest
from google.genai import errors as genai_errors

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

from pipelex.cogt.exceptions import InferenceErrorCategory, LLMCompletionError, LLMModelNotFoundError
from pipelex.cogt.inference.error_classification import UserActionKind
from pipelex.providers.google.google_llm_worker import GoogleLLMWorker
from tests.helpers.instructor_test_utils import DummySchema, make_llm_job, wrap_in_instructor_retry


def _mock_response(status_code: int, headers: dict[str, str] | None = None) -> httpx.Response:
    request = httpx.Request("POST", "https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent")
    return httpx.Response(status_code=status_code, request=request, headers=headers or {})


def _make_client_error(
    code: int,
    message: str,
    *,
    status: str | None = None,
    headers: dict[str, str] | None = None,
) -> genai_errors.ClientError:
    response_json: dict[str, object] = {
        "error": {
            "code": code,
            "message": message,
            "status": status if status is not None else "ERROR",
        },
    }
    return genai_errors.ClientError(code, response_json, _mock_response(code, headers=headers))


def _make_server_error(code: int, message: str) -> genai_errors.ServerError:
    response_json: dict[str, object] = {
        "error": {"code": code, "message": message, "status": "INTERNAL"},
    }
    return genai_errors.ServerError(code, response_json, _mock_response(code))


def _make_worker(mocker: MockerFixture) -> GoogleLLMWorker:
    worker = object.__new__(GoogleLLMWorker)
    mock_model = mocker.MagicMock()
    mock_model.desc = "test-model-desc"
    mock_model.model_id = "gemini-pro"
    mock_model.name = "gemini-pro"
    mock_model.thinking_mode = None
    worker.inference_model = mock_model

    instructor_client = mocker.MagicMock()
    instructor_client.chat.completions.create_with_completion = mocker.AsyncMock()
    worker.instructor_for_objects = instructor_client

    mocker.patch(
        "pipelex.providers.google.google_llm_worker.GoogleFactory.prepare_user_contents",
        new_callable=mocker.AsyncMock,
        return_value=[],
    )

    return worker


@pytest.mark.asyncio(loop_scope="class")
class TestGoogleLLMWorkerObjectErrorHandling:
    """``_gen_object`` must categorize SDK errors that ``instructor`` wraps in ``InstructorRetryException``."""

    async def test_wrapped_server_error_is_transient(self, mocker: MockerFixture) -> None:
        worker = _make_worker(mocker)
        sdk_exc = _make_server_error(500, "Internal server error")
        wrapped = wrap_in_instructor_retry(sdk_exc)
        worker.instructor_for_objects.chat.completions.create_with_completion.side_effect = wrapped  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(LLMCompletionError) as exc_info:
            await worker._gen_object(llm_job=make_llm_job(mocker), schema=DummySchema)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.TRANSIENT
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.WAIT_AND_RETRY
        assert exc_info.value.__cause__ is wrapped
        metadata = exc_info.value.provider_metadata
        assert metadata is not None
        assert metadata.provider == "google"
        assert metadata.sdk_exception_type == "ServerError"
        assert metadata.status_code == 500

    async def test_wrapped_rate_limit_generic_is_transient(self, mocker: MockerFixture) -> None:
        worker = _make_worker(mocker)
        sdk_exc = _make_client_error(
            429,
            "Too many requests",
            headers={"x-goog-request-id": "req_rate", "retry-after": "5"},
        )
        wrapped = wrap_in_instructor_retry(sdk_exc)
        worker.instructor_for_objects.chat.completions.create_with_completion.side_effect = wrapped  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(LLMCompletionError) as exc_info:
            await worker._gen_object(llm_job=make_llm_job(mocker), schema=DummySchema)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.TRANSIENT
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.WAIT_AND_RETRY
        assert "retry" in exc_info.value.user_action.detail.lower()
        metadata = exc_info.value.provider_metadata
        assert metadata is not None
        assert metadata.status_code == 429
        assert metadata.request_id == "req_rate"
        assert metadata.retry_after_seconds == 5.0

    async def test_wrapped_rate_limit_quota_is_capacity(self, mocker: MockerFixture) -> None:
        worker = _make_worker(mocker)
        sdk_exc = _make_client_error(
            429,
            "Resource has been exhausted (e.g. check quota)",
            status="RESOURCE_EXHAUSTED",
        )
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
        assert metadata.provider_error_code == "RESOURCE_EXHAUSTED"

    async def test_wrapped_bad_request_content_policy(self, mocker: MockerFixture) -> None:
        worker = _make_worker(mocker)
        sdk_exc = _make_client_error(400, "Your request was rejected due to content_policy_violation")
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

    async def test_wrapped_bad_request_generic_is_content(self, mocker: MockerFixture) -> None:
        worker = _make_worker(mocker)
        sdk_exc = _make_client_error(400, "Invalid parameter: temperature must be between 0 and 2")
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
        sdk_exc = _make_client_error(401, "Request had invalid authentication credentials", status="UNAUTHENTICATED")
        wrapped = wrap_in_instructor_retry(sdk_exc)
        worker.instructor_for_objects.chat.completions.create_with_completion.side_effect = wrapped  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(LLMCompletionError) as exc_info:
            await worker._gen_object(llm_job=make_llm_job(mocker), schema=DummySchema)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.CONFIGURATION
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.CHECK_CREDENTIALS
        metadata = exc_info.value.provider_metadata
        assert metadata is not None
        assert metadata.status_code == 401

    async def test_wrapped_forbidden_is_configuration(self, mocker: MockerFixture) -> None:
        worker = _make_worker(mocker)
        sdk_exc = _make_client_error(403, "Permission denied", status="PERMISSION_DENIED")
        wrapped = wrap_in_instructor_retry(sdk_exc)
        worker.instructor_for_objects.chat.completions.create_with_completion.side_effect = wrapped  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(LLMCompletionError) as exc_info:
            await worker._gen_object(llm_job=make_llm_job(mocker), schema=DummySchema)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.CONFIGURATION
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.CHECK_CREDENTIALS
        metadata = exc_info.value.provider_metadata
        assert metadata is not None
        assert metadata.status_code == 403

    async def test_wrapped_not_found_raises_llm_model_not_found_error(self, mocker: MockerFixture) -> None:
        worker = _make_worker(mocker)
        sdk_exc = _make_client_error(404, "Model gemini-99 not found", status="NOT_FOUND")
        wrapped = wrap_in_instructor_retry(sdk_exc)
        worker.instructor_for_objects.chat.completions.create_with_completion.side_effect = wrapped  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(LLMModelNotFoundError) as exc_info:
            await worker._gen_object(llm_job=make_llm_job(mocker), schema=DummySchema)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.CONFIGURATION
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.CHANGE_MODEL
        metadata = exc_info.value.provider_metadata
        assert metadata is not None
        assert metadata.status_code == 404

    async def test_unrecognized_underlying_falls_back_to_unknown(self, mocker: MockerFixture) -> None:
        """A wrapped non-SDK exception (e.g. schema validation) routes to UNKNOWN, not CONTENT."""
        worker = _make_worker(mocker)
        wrapped = wrap_in_instructor_retry(ValueError("Schema validation failed"))
        worker.instructor_for_objects.chat.completions.create_with_completion.side_effect = wrapped  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(LLMCompletionError) as exc_info:
            await worker._gen_object(llm_job=make_llm_job(mocker), schema=DummySchema)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.UNKNOWN
        assert exc_info.value.__cause__ is wrapped
        assert exc_info.value.provider_metadata is not None
        assert exc_info.value.provider_metadata.sdk_exception_type == "ValueError"
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.CONTACT_SUPPORT

    async def test_real_instructor_propagates_client_error_raw(self, mocker: MockerFixture) -> None:
        """End-to-end: drive the real instructor library with a ``ClientError`` and verify the
        W2.3 behavior — instructor, confined to schema re-ask, does NOT retry the transport error
        and does NOT wrap it in ``InstructorRetryException``. It propagates as the raw
        ``ClientError``, which the worker classifies as TRANSIENT with provider metadata.
        """
        import instructor  # ruff: ignore[import-outside-top-level]
        from google.genai import Client as GoogleGenAiClient  # ruff: ignore[import-outside-top-level]

        worker = _make_worker(mocker)

        # Override the conftest-style empty contents with a real ``Content`` —
        # instructor's gemini message converter rejects a bare ``list`` (which is
        # what the empty default produces once wrapped in ``messages=[...]``).
        from google.genai import types as genai_types  # ruff: ignore[import-outside-top-level]

        user_content = genai_types.Content(role="user", parts=[genai_types.Part.from_text(text="hi")])
        mocker.patch(
            "pipelex.providers.google.google_llm_worker.GoogleFactory.prepare_user_contents",
            new_callable=mocker.AsyncMock,
            return_value=user_content,
        )

        genai_client = GoogleGenAiClient(api_key="fake")
        sdk_exc = _make_client_error(429, "Too many requests")
        genai_client.aio.models.generate_content = mocker.AsyncMock(side_effect=sdk_exc)  # type: ignore[method-assign]  # pyright: ignore[reportAttributeAccessIssue]
        worker.instructor_for_objects = instructor.from_genai(client=genai_client, use_async=True)

        with pytest.raises(LLMCompletionError) as exc_info:
            await worker._gen_object(llm_job=make_llm_job(mocker), schema=DummySchema)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.TRANSIENT
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.WAIT_AND_RETRY
        metadata = exc_info.value.provider_metadata
        assert metadata is not None
        assert metadata.provider == "google"
        assert metadata.status_code == 429
        # The raw SDK exception propagates and chains directly — instructor no longer wraps it.
        assert exc_info.value.__cause__ is sdk_exc

    @pytest.mark.parametrize(
        ("sdk_exc", "expected_category"),
        [
            (_make_server_error(500, "Internal server error"), InferenceErrorCategory.TRANSIENT),
            (_make_server_error(503, "Service unavailable"), InferenceErrorCategory.TRANSIENT),
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
        """W2.3 regression: a raw SDK / httpx transport exception from ``create_with_completion`` is
        classified, never flattened to ``UNKNOWN``. The ``httpx`` cases cover the Google GenAI SDK's
        habit of letting raw connection / timeout errors propagate — they are NOT wrapped into
        ``ServerError`` / ``ClientError`` — which the worker's widened ``except`` clause now catches.
        """
        worker = _make_worker(mocker)
        worker.instructor_for_objects.chat.completions.create_with_completion.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(LLMCompletionError) as exc_info:
            await worker._gen_object(llm_job=make_llm_job(mocker), schema=DummySchema)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is expected_category
        assert exc_info.value.__cause__ is sdk_exc
