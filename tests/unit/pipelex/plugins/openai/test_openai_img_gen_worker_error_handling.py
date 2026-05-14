"""Tests for OpenAI ImgGen worker SDK exception handling and error categorization."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx
import openai
import pytest

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

from pipelex.cogt.exceptions import ImgGenGenerationError, ImgGenModelNotFoundError, InferenceErrorCategory
from pipelex.cogt.inference.error_classification import UserActionKind
from pipelex.plugins.openai.openai_img_gen_worker import OpenAIImgGenWorker


def _make_response(status_code: int, headers: dict[str, str] | None = None) -> httpx.Response:
    request = httpx.Request("POST", "https://api.openai.com/v1/images/generations")
    return httpx.Response(status_code=status_code, request=request, headers=headers or {})


def _make_openai_img_gen_worker(mocker: MockerFixture) -> OpenAIImgGenWorker:
    """Create a minimal OpenAIImgGenWorker with mocked internals."""
    worker = object.__new__(OpenAIImgGenWorker)
    mock_model = mocker.MagicMock()
    mock_model.desc = "test-openai-img-model"
    mock_model.model_id = "gpt-image-1"
    mock_model.name = "gpt-image-1"
    mock_model.rules = mocker.MagicMock()
    worker.inference_model = mock_model

    mock_client = mocker.MagicMock()
    mock_client.images.generate = mocker.AsyncMock()
    mock_client.images.edit = mocker.AsyncMock()
    worker.openai_client = mock_client

    return worker


def _make_img_gen_job(mocker: MockerFixture) -> Any:
    job = mocker.MagicMock()
    job.img_gen_prompt.positive_text = "a sunset over mountains"
    job.job_report.img_gen_tokens_usage = None
    return job


@pytest.mark.asyncio(loop_scope="class")
class TestOpenAIImgGenWorkerErrorHandling:
    """Verifies categorization, metadata extraction, and semantic UserActionKind values."""

    async def test_rate_limit_is_transient_with_wait_and_retry(self, mocker: MockerFixture) -> None:
        worker = _make_openai_img_gen_worker(mocker)
        sdk_exc = openai.RateLimitError(
            "rate limited",
            response=_make_response(429, headers={"x-request-id": "req_rl_1"}),
            body={"type": "rate_limit_error", "code": "rate_limit_exceeded"},
        )
        worker.openai_client.images.generate.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        mocker.patch(
            "pipelex.plugins.openai.openai_img_gen_worker.ImgGenArgsFactory.make_args_for_model",
            new_callable=mocker.AsyncMock,
            return_value={"prompt": "test"},
        )

        with pytest.raises(ImgGenGenerationError) as exc_info:
            await worker._gen_image_list(img_gen_job=_make_img_gen_job(mocker), nb_images=1)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.TRANSIENT
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.WAIT_AND_RETRY
        assert exc_info.value.provider_metadata is not None
        assert exc_info.value.provider_metadata.status_code == 429
        assert exc_info.value.provider_metadata.request_id == "req_rl_1"
        assert exc_info.value.__cause__ is sdk_exc

    async def test_quota_exhausted_is_capacity_with_check_billing(self, mocker: MockerFixture) -> None:
        worker = _make_openai_img_gen_worker(mocker)
        sdk_exc = openai.RateLimitError(
            "You exceeded your current quota, please check your plan and billing details. insufficient_quota",
            response=_make_response(429),
            body={"type": "insufficient_quota", "code": "insufficient_quota"},
        )
        worker.openai_client.images.generate.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        mocker.patch(
            "pipelex.plugins.openai.openai_img_gen_worker.ImgGenArgsFactory.make_args_for_model",
            new_callable=mocker.AsyncMock,
            return_value={"prompt": "test"},
        )

        with pytest.raises(ImgGenGenerationError) as exc_info:
            await worker._gen_image_list(img_gen_job=_make_img_gen_job(mocker), nb_images=1)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.CAPACITY
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.CHECK_BILLING
        assert exc_info.value.provider_metadata is not None
        assert exc_info.value.provider_metadata.status_code == 429

    async def test_timeout_is_transient(self, mocker: MockerFixture) -> None:
        worker = _make_openai_img_gen_worker(mocker)
        request = httpx.Request("POST", "https://api.openai.com/v1/images/generations")
        sdk_exc = openai.APITimeoutError(request=request)
        worker.openai_client.images.generate.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        mocker.patch(
            "pipelex.plugins.openai.openai_img_gen_worker.ImgGenArgsFactory.make_args_for_model",
            new_callable=mocker.AsyncMock,
            return_value={"prompt": "test"},
        )

        with pytest.raises(ImgGenGenerationError) as exc_info:
            await worker._gen_image_list(img_gen_job=_make_img_gen_job(mocker), nb_images=1)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.TRANSIENT
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.WAIT_AND_RETRY
        assert exc_info.value.provider_metadata is not None
        assert exc_info.value.provider_metadata.sdk_exception_type == "APITimeoutError"

    async def test_connection_error_is_transient(self, mocker: MockerFixture) -> None:
        worker = _make_openai_img_gen_worker(mocker)
        request = httpx.Request("POST", "https://api.openai.com/v1/images/generations")
        sdk_exc = openai.APIConnectionError(message="Connection refused", request=request)
        worker.openai_client.images.generate.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        mocker.patch(
            "pipelex.plugins.openai.openai_img_gen_worker.ImgGenArgsFactory.make_args_for_model",
            new_callable=mocker.AsyncMock,
            return_value={"prompt": "test"},
        )

        with pytest.raises(ImgGenGenerationError) as exc_info:
            await worker._gen_image_list(img_gen_job=_make_img_gen_job(mocker), nb_images=1)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.TRANSIENT
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.WAIT_AND_RETRY

    async def test_internal_server_error_is_transient(self, mocker: MockerFixture) -> None:
        worker = _make_openai_img_gen_worker(mocker)
        sdk_exc = openai.InternalServerError(
            "server error",
            response=_make_response(500),
            body={"type": "server_error", "code": "internal_error"},
        )
        worker.openai_client.images.generate.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        mocker.patch(
            "pipelex.plugins.openai.openai_img_gen_worker.ImgGenArgsFactory.make_args_for_model",
            new_callable=mocker.AsyncMock,
            return_value={"prompt": "test"},
        )

        with pytest.raises(ImgGenGenerationError) as exc_info:
            await worker._gen_image_list(img_gen_job=_make_img_gen_job(mocker), nb_images=1)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.TRANSIENT
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.WAIT_AND_RETRY
        assert exc_info.value.provider_metadata is not None
        assert exc_info.value.provider_metadata.status_code == 500

    async def test_content_policy_bad_request_is_content_change_input(self, mocker: MockerFixture) -> None:
        worker = _make_openai_img_gen_worker(mocker)
        sdk_exc = openai.BadRequestError(
            "Your request was rejected as a result of our safety system",
            response=_make_response(400),
            body={"type": "image_generation_user_error", "code": "content_policy_violation"},
        )
        worker.openai_client.images.generate.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        mocker.patch(
            "pipelex.plugins.openai.openai_img_gen_worker.ImgGenArgsFactory.make_args_for_model",
            new_callable=mocker.AsyncMock,
            return_value={"prompt": "test"},
        )

        with pytest.raises(ImgGenGenerationError) as exc_info:
            await worker._gen_image_list(img_gen_job=_make_img_gen_job(mocker), nb_images=1)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.CONTENT
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.CHANGE_INPUT

    async def test_generic_bad_request_is_content_change_input(self, mocker: MockerFixture) -> None:
        worker = _make_openai_img_gen_worker(mocker)
        sdk_exc = openai.BadRequestError(
            "missing required field",
            response=_make_response(400),
            body={"type": "invalid_request_error", "code": "missing_field"},
        )
        worker.openai_client.images.generate.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        mocker.patch(
            "pipelex.plugins.openai.openai_img_gen_worker.ImgGenArgsFactory.make_args_for_model",
            new_callable=mocker.AsyncMock,
            return_value={"prompt": "test"},
        )

        with pytest.raises(ImgGenGenerationError) as exc_info:
            await worker._gen_image_list(img_gen_job=_make_img_gen_job(mocker), nb_images=1)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.CONTENT
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.CHANGE_INPUT

    async def test_authentication_error_is_configuration_check_credentials(self, mocker: MockerFixture) -> None:
        worker = _make_openai_img_gen_worker(mocker)
        sdk_exc = openai.AuthenticationError(
            "invalid api key",
            response=_make_response(401),
            body={"type": "invalid_request_error", "code": "invalid_api_key"},
        )
        worker.openai_client.images.generate.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        mocker.patch(
            "pipelex.plugins.openai.openai_img_gen_worker.ImgGenArgsFactory.make_args_for_model",
            new_callable=mocker.AsyncMock,
            return_value={"prompt": "test"},
        )

        with pytest.raises(ImgGenGenerationError) as exc_info:
            await worker._gen_image_list(img_gen_job=_make_img_gen_job(mocker), nb_images=1)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.CONFIGURATION
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.CHECK_CREDENTIALS
        assert exc_info.value.provider_metadata is not None
        assert exc_info.value.provider_metadata.status_code == 401

    async def test_permission_denied_is_configuration_check_credentials(self, mocker: MockerFixture) -> None:
        worker = _make_openai_img_gen_worker(mocker)
        sdk_exc = openai.PermissionDeniedError(
            "permission denied",
            response=_make_response(403),
            body={"type": "permission_denied", "code": "permission_denied"},
        )
        worker.openai_client.images.generate.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        mocker.patch(
            "pipelex.plugins.openai.openai_img_gen_worker.ImgGenArgsFactory.make_args_for_model",
            new_callable=mocker.AsyncMock,
            return_value={"prompt": "test"},
        )

        with pytest.raises(ImgGenGenerationError) as exc_info:
            await worker._gen_image_list(img_gen_job=_make_img_gen_job(mocker), nb_images=1)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.CONFIGURATION
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.CHECK_CREDENTIALS

    async def test_not_found_raises_img_gen_model_not_found_error_with_change_model(self, mocker: MockerFixture) -> None:
        worker = _make_openai_img_gen_worker(mocker)
        sdk_exc = openai.NotFoundError(
            "model not found",
            response=_make_response(404),
            body={"type": "invalid_request_error", "code": "model_not_found"},
        )
        worker.openai_client.images.generate.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        mocker.patch(
            "pipelex.plugins.openai.openai_img_gen_worker.ImgGenArgsFactory.make_args_for_model",
            new_callable=mocker.AsyncMock,
            return_value={"prompt": "test"},
        )

        with pytest.raises(ImgGenModelNotFoundError) as exc_info:
            await worker._gen_image_list(img_gen_job=_make_img_gen_job(mocker), nb_images=1)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.CONFIGURATION
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.CHANGE_MODEL
        assert exc_info.value.provider_metadata is not None
        assert exc_info.value.provider_metadata.status_code == 404
        assert exc_info.value.model_handle == "gpt-image-1"

    async def test_error_report_includes_provider_metadata(self, mocker: MockerFixture) -> None:
        worker = _make_openai_img_gen_worker(mocker)
        sdk_exc = openai.RateLimitError(
            "rate limited",
            response=_make_response(429, headers={"retry-after": "5"}),
            body={"type": "rate_limit_error", "code": "rate_limit_exceeded"},
        )
        worker.openai_client.images.generate.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        mocker.patch(
            "pipelex.plugins.openai.openai_img_gen_worker.ImgGenArgsFactory.make_args_for_model",
            new_callable=mocker.AsyncMock,
            return_value={"prompt": "test"},
        )

        with pytest.raises(ImgGenGenerationError) as exc_info:
            await worker._gen_image_list(img_gen_job=_make_img_gen_job(mocker), nb_images=1)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        report = exc_info.value.to_error_report()
        assert report.error_category == "transient"
        assert report.retryable is True
        assert report.provider_metadata is not None
        assert report.provider_metadata.provider == "openai"
        assert report.provider_metadata.status_code == 429
        assert report.provider_metadata.retry_after_seconds == 5.0
