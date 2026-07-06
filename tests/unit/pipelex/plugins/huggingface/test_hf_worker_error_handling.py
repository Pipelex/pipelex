"""Tests for HuggingFace ImgGen worker SDK exception handling and error categorization."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx
import pytest
from huggingface_hub.errors import HfHubHTTPError, InferenceTimeoutError

from pipelex.cogt.exceptions import ImgGenGenerationError, InferenceErrorCategory
from pipelex.cogt.inference.error_classification import UserActionKind
from pipelex.plugins.huggingface.huggingface_img_gen_worker import HuggingFaceImgGenWorker
from tests.unit.pipelex.plugins.huggingface.test_data import HuggingFaceErrorHandlingTestData

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


def _make_hf_http_error(status_code: int | None, message: str) -> HfHubHTTPError:
    """Create a minimal HfHubHTTPError for testing with optional status code."""
    response = httpx.Response(
        status_code=status_code or 500,
        request=httpx.Request("POST", "https://router.huggingface.co/test"),
    )
    exc = HfHubHTTPError(message, response=response)
    if status_code is None:
        # Simulate a network-level failure carrying no response metadata
        exc.response = None  # type: ignore[assignment]  # pyright: ignore[reportAttributeAccessIssue]
    return exc


def _make_inference_timeout_error(message: str = "Inference timed out") -> InferenceTimeoutError:
    """Create a minimal InferenceTimeoutError for testing."""
    return InferenceTimeoutError(message)


def _make_hf_img_gen_worker(mocker: MockerFixture) -> HuggingFaceImgGenWorker:
    """Create a minimal HuggingFaceImgGenWorker with mocked internals."""
    worker = object.__new__(HuggingFaceImgGenWorker)
    mock_model = mocker.MagicMock()
    mock_model.desc = "test-hf-model"
    mock_model.model_id = "stabilityai/stable-diffusion-xl-base-1.0"
    mock_model.name = "sdxl-base"
    mock_model.rules = mocker.MagicMock()
    worker.inference_model = mock_model

    mock_client = mocker.MagicMock()
    mock_client.text_to_image = mocker.AsyncMock()
    worker.hf_async_client = mock_client

    return worker


def _make_img_gen_job(mocker: MockerFixture) -> Any:
    """Create a mock ImgGen job."""
    job = mocker.MagicMock()
    job.img_gen_prompt.positive_text = "a sunset over mountains"
    job.job_params.output_format = None
    job.job_report.img_gen_tokens_usage = None
    return job


@pytest.mark.asyncio(loop_scope="class")
class TestHuggingFaceWorkerErrorHandling:
    """Tests for HuggingFace ImgGen worker SDK exception handling and error categorization."""

    @pytest.mark.parametrize(
        ("_topic", "status_code", "message", "expected_category", "expected_user_action_kind"),
        HuggingFaceErrorHandlingTestData.HF_HTTP_ERROR_CASES,
    )
    async def test_hf_http_error_categorization(
        self,
        mocker: MockerFixture,
        _topic: str,
        status_code: int | None,
        message: str,
        expected_category: InferenceErrorCategory,
        expected_user_action_kind: UserActionKind,
    ) -> None:
        """HfHubHTTPError is caught and categorized correctly based on status code."""
        worker = _make_hf_img_gen_worker(mocker)
        sdk_exc = _make_hf_http_error(status_code, message)
        worker.hf_async_client.text_to_image.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        mocker.patch(
            "pipelex.plugins.huggingface.huggingface_img_gen_worker.ImgGenArgsFactory.make_args_for_model",
            new_callable=mocker.AsyncMock,
            return_value={"prompt": "test", "model": "test-model-id"},
        )

        with pytest.raises(ImgGenGenerationError) as exc_info:
            await worker._generate_single_image(img_gen_job=_make_img_gen_job(mocker))  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is expected_category
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is expected_user_action_kind
        assert exc_info.value.__cause__ is sdk_exc

    @pytest.mark.parametrize(
        ("_topic", "expected_category", "expected_user_action_kind"),
        HuggingFaceErrorHandlingTestData.TIMEOUT_CASES,
    )
    async def test_inference_timeout_is_transient(
        self,
        mocker: MockerFixture,
        _topic: str,
        expected_category: InferenceErrorCategory,
        expected_user_action_kind: UserActionKind,
    ) -> None:
        """InferenceTimeoutError is caught and categorized as TRANSIENT."""
        worker = _make_hf_img_gen_worker(mocker)
        sdk_exc = _make_inference_timeout_error()
        worker.hf_async_client.text_to_image.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        mocker.patch(
            "pipelex.plugins.huggingface.huggingface_img_gen_worker.ImgGenArgsFactory.make_args_for_model",
            new_callable=mocker.AsyncMock,
            return_value={"prompt": "test", "model": "test-model-id"},
        )

        with pytest.raises(ImgGenGenerationError) as exc_info:
            await worker._generate_single_image(img_gen_job=_make_img_gen_job(mocker))  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is expected_category
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is expected_user_action_kind
        assert exc_info.value.__cause__ is sdk_exc

    async def test_error_report_includes_category(self, mocker: MockerFixture) -> None:
        """to_error_report() includes error_category and retryable from the exception."""
        worker = _make_hf_img_gen_worker(mocker)
        sdk_exc = _make_hf_http_error(401, "Invalid token")
        worker.hf_async_client.text_to_image.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        mocker.patch(
            "pipelex.plugins.huggingface.huggingface_img_gen_worker.ImgGenArgsFactory.make_args_for_model",
            new_callable=mocker.AsyncMock,
            return_value={"prompt": "test", "model": "test-model-id"},
        )

        with pytest.raises(ImgGenGenerationError) as exc_info:
            await worker._generate_single_image(img_gen_job=_make_img_gen_job(mocker))  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        report = exc_info.value.to_error_report()
        assert report.error_category == "configuration"
        assert report.retryable is False
        assert report.error_type == "ImgGenGenerationError"
        assert exc_info.value.error_category is InferenceErrorCategory.CONFIGURATION
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.CHECK_CREDENTIALS
