"""Tests for OpenAI Completions ImgGen worker SDK exception handling and error categorization."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx
import openai
import pytest

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

from pipelex.cogt.exceptions import ImgGenGenerationError, ImgGenModelNotFoundError, InferenceErrorCategory
from pipelex.cogt.inference.error_classification import UserActionKind
from pipelex.plugins.openai.openai_completions_img_gen_worker import OpenAICompletionsImgGenWorker


def _make_response(status_code: int, headers: dict[str, str] | None = None) -> httpx.Response:
    request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    return httpx.Response(status_code=status_code, request=request, headers=headers or {})


def _make_worker(mocker: MockerFixture) -> OpenAICompletionsImgGenWorker:
    """Create a minimal worker with mocked internals."""
    worker = object.__new__(OpenAICompletionsImgGenWorker)
    mock_model = mocker.MagicMock()
    mock_model.desc = "test-openai-completions-img"
    mock_model.model_id = "gemini-2.5-flash-image-preview"
    mock_model.name = "gemini-2.5-flash-image-preview"
    mock_model.backend_name = "openrouter"
    mock_model.tag = "test-tag"
    worker.inference_model = mock_model

    mock_client = mocker.MagicMock()
    mock_client.chat.completions.create = mocker.AsyncMock()
    worker.openai_client = mock_client

    mock_factory = mocker.MagicMock()
    mock_factory.make_extras.return_value = ({}, {})
    worker.openai_completions_factory = mock_factory

    return worker


def _make_img_gen_job(mocker: MockerFixture) -> Any:
    job = mocker.MagicMock()
    job.img_gen_prompt.positive_text = "a sunset over mountains"
    job.img_gen_prompt.input_images = None
    job.job_params.output_format = None
    job.job_report.img_gen_tokens_usage = None
    return job


@pytest.mark.asyncio(loop_scope="class")
class TestOpenAICompletionsImgGenWorkerErrorHandling:
    """Verifies categorization, metadata, and semantic UserActionKind values."""

    async def test_rate_limit_is_transient(self, mocker: MockerFixture) -> None:
        worker = _make_worker(mocker)
        sdk_exc = openai.RateLimitError(
            "rate limited",
            response=_make_response(429, headers={"x-request-id": "req_1"}),
            body={"type": "rate_limit_error", "code": "rate_limit_exceeded"},
        )
        worker.openai_client.chat.completions.create.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(ImgGenGenerationError) as exc_info:
            await worker._gen_image(img_gen_job=_make_img_gen_job(mocker))  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.TRANSIENT
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.WAIT_AND_RETRY
        assert exc_info.value.provider_metadata is not None
        assert exc_info.value.provider_metadata.status_code == 429

    async def test_quota_is_capacity_check_billing(self, mocker: MockerFixture) -> None:
        worker = _make_worker(mocker)
        sdk_exc = openai.RateLimitError(
            "You exceeded your current quota - insufficient_quota",
            response=_make_response(429),
            body={"type": "insufficient_quota", "code": "insufficient_quota"},
        )
        worker.openai_client.chat.completions.create.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(ImgGenGenerationError) as exc_info:
            await worker._gen_image(img_gen_job=_make_img_gen_job(mocker))  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.CAPACITY
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.CHECK_BILLING

    async def test_timeout_is_transient(self, mocker: MockerFixture) -> None:
        worker = _make_worker(mocker)
        request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
        sdk_exc = openai.APITimeoutError(request=request)
        worker.openai_client.chat.completions.create.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(ImgGenGenerationError) as exc_info:
            await worker._gen_image(img_gen_job=_make_img_gen_job(mocker))  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.TRANSIENT
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.WAIT_AND_RETRY

    async def test_connection_error_is_transient(self, mocker: MockerFixture) -> None:
        worker = _make_worker(mocker)
        request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
        sdk_exc = openai.APIConnectionError(message="boom", request=request)
        worker.openai_client.chat.completions.create.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(ImgGenGenerationError) as exc_info:
            await worker._gen_image(img_gen_job=_make_img_gen_job(mocker))  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.TRANSIENT

    async def test_server_error_is_transient(self, mocker: MockerFixture) -> None:
        worker = _make_worker(mocker)
        sdk_exc = openai.InternalServerError("server error", response=_make_response(500), body={"type": "server_error"})
        worker.openai_client.chat.completions.create.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(ImgGenGenerationError) as exc_info:
            await worker._gen_image(img_gen_job=_make_img_gen_job(mocker))  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.TRANSIENT
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.WAIT_AND_RETRY

    async def test_content_policy_bad_request_is_content_change_input(self, mocker: MockerFixture) -> None:
        worker = _make_worker(mocker)
        sdk_exc = openai.BadRequestError(
            "blocked by safety filter",
            response=_make_response(400),
            body={"type": "image_generation_user_error", "code": "content_policy_violation"},
        )
        worker.openai_client.chat.completions.create.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(ImgGenGenerationError) as exc_info:
            await worker._gen_image(img_gen_job=_make_img_gen_job(mocker))  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.CONTENT
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.CHANGE_INPUT

    async def test_generic_bad_request_is_content_change_input(self, mocker: MockerFixture) -> None:
        worker = _make_worker(mocker)
        sdk_exc = openai.BadRequestError(
            "missing field",
            response=_make_response(400),
            body={"type": "invalid_request_error", "code": "missing_field"},
        )
        worker.openai_client.chat.completions.create.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(ImgGenGenerationError) as exc_info:
            await worker._gen_image(img_gen_job=_make_img_gen_job(mocker))  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.CONTENT
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.CHANGE_INPUT

    async def test_auth_error_is_configuration_check_credentials(self, mocker: MockerFixture) -> None:
        worker = _make_worker(mocker)
        sdk_exc = openai.AuthenticationError(
            "bad key",
            response=_make_response(401),
            body={"type": "invalid_request_error", "code": "invalid_api_key"},
        )
        worker.openai_client.chat.completions.create.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(ImgGenGenerationError) as exc_info:
            await worker._gen_image(img_gen_job=_make_img_gen_job(mocker))  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.CONFIGURATION
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.CHECK_CREDENTIALS

    async def test_permission_denied_is_configuration_check_credentials(self, mocker: MockerFixture) -> None:
        worker = _make_worker(mocker)
        sdk_exc = openai.PermissionDeniedError(
            "permission denied",
            response=_make_response(403),
            body={"type": "permission_denied", "code": "permission_denied"},
        )
        worker.openai_client.chat.completions.create.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(ImgGenGenerationError) as exc_info:
            await worker._gen_image(img_gen_job=_make_img_gen_job(mocker))  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.CONFIGURATION
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.CHECK_CREDENTIALS

    async def test_not_found_raises_img_gen_model_not_found_error_with_change_model(self, mocker: MockerFixture) -> None:
        worker = _make_worker(mocker)
        sdk_exc = openai.NotFoundError(
            "model not found",
            response=_make_response(404),
            body={"type": "invalid_request_error", "code": "model_not_found"},
        )
        worker.openai_client.chat.completions.create.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(ImgGenModelNotFoundError) as exc_info:
            await worker._gen_image(img_gen_job=_make_img_gen_job(mocker))  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.CONFIGURATION
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.CHANGE_MODEL
        assert exc_info.value.provider_metadata is not None
        assert exc_info.value.provider_metadata.status_code == 404

    async def test_generic_status_error_409_is_configuration(self, mocker: MockerFixture) -> None:
        """An unhandled 4xx APIStatusError (409 Conflict) is categorized CONFIGURATION via the generic fallback."""
        worker = _make_worker(mocker)
        sdk_exc = openai.ConflictError("conflict", response=_make_response(409), body=None)
        worker.openai_client.chat.completions.create.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(ImgGenGenerationError) as exc_info:
            await worker._gen_image(img_gen_job=_make_img_gen_job(mocker))  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.CONFIGURATION
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.CHANGE_INPUT
        assert exc_info.value.provider_metadata is not None
        assert exc_info.value.provider_metadata.status_code == 409

    async def test_generic_status_error_503_is_transient(self, mocker: MockerFixture) -> None:
        """An unhandled 5xx APIStatusError is categorized TRANSIENT via the generic fallback."""
        worker = _make_worker(mocker)
        sdk_exc = openai.APIStatusError("service unavailable", response=_make_response(503), body=None)
        worker.openai_client.chat.completions.create.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(ImgGenGenerationError) as exc_info:
            await worker._gen_image(img_gen_job=_make_img_gen_job(mocker))  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.TRANSIENT
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.WAIT_AND_RETRY
        assert exc_info.value.provider_metadata is not None
        assert exc_info.value.provider_metadata.status_code == 503
