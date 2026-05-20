"""Tests asserting provider_metadata + semantic UserActionKind on HF ImgGen errors."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from huggingface_hub.errors import HfHubHTTPError, InferenceTimeoutError

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

from pipelex.cogt.exceptions import ImgGenGenerationError, ImgGenModelNotFoundError, InferenceErrorCategory
from pipelex.cogt.inference.error_classification import UserActionKind
from pipelex.plugins.huggingface.huggingface_img_gen_worker import HuggingFaceImgGenWorker


def _make_hf_http_error(status_code: int, message: str = "error") -> HfHubHTTPError:
    import requests  # noqa: PLC0415

    response = requests.Response()
    response.status_code = status_code
    exc = HfHubHTTPError(message=message)
    exc.response = response  # type: ignore[attr-defined]
    return exc


def _make_worker(mocker: MockerFixture) -> HuggingFaceImgGenWorker:
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
    job = mocker.MagicMock()
    job.img_gen_prompt.positive_text = "test prompt"
    job.job_params.output_format = None
    job.job_report.img_gen_tokens_usage = None
    return job


@pytest.mark.asyncio(loop_scope="class")
class TestHuggingFaceImgGenWorkerSemantic:
    """Each branch carries semantic UserActionKind + provider_metadata."""

    @pytest.mark.parametrize(
        ("status_code", "expected_category", "expected_kind"),
        [
            (429, InferenceErrorCategory.TRANSIENT, UserActionKind.WAIT_AND_RETRY),
            (402, InferenceErrorCategory.CAPACITY, UserActionKind.CHECK_BILLING),
            (401, InferenceErrorCategory.CONFIGURATION, UserActionKind.CHECK_CREDENTIALS),
            (403, InferenceErrorCategory.CONFIGURATION, UserActionKind.CHECK_CREDENTIALS),
            (400, InferenceErrorCategory.CONTENT, UserActionKind.CHANGE_INPUT),
            # Unhandled 4xx: non-retryable client error, not TRANSIENT.
            (409, InferenceErrorCategory.CONFIGURATION, UserActionKind.CHANGE_INPUT),
            (422, InferenceErrorCategory.CONFIGURATION, UserActionKind.CHANGE_INPUT),
            (500, InferenceErrorCategory.TRANSIENT, UserActionKind.WAIT_AND_RETRY),
        ],
    )
    async def test_http_error_carries_semantic_user_action(
        self,
        mocker: MockerFixture,
        status_code: int,
        expected_category: InferenceErrorCategory,
        expected_kind: UserActionKind,
    ) -> None:
        worker = _make_worker(mocker)
        sdk_exc = _make_hf_http_error(status_code, message=f"http {status_code}")
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
        assert exc_info.value.user_action.kind is expected_kind
        assert exc_info.value.provider_metadata is not None
        assert exc_info.value.provider_metadata.provider == "huggingface"
        assert exc_info.value.provider_metadata.status_code == status_code

    async def test_not_found_404_raises_img_gen_model_not_found_error(self, mocker: MockerFixture) -> None:
        """A 404 specializes to ImgGenModelNotFoundError (CONFIGURATION, CHANGE_MODEL)."""
        worker = _make_worker(mocker)
        sdk_exc = _make_hf_http_error(404, message="model not found")
        worker.hf_async_client.text_to_image.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        mocker.patch(
            "pipelex.plugins.huggingface.huggingface_img_gen_worker.ImgGenArgsFactory.make_args_for_model",
            new_callable=mocker.AsyncMock,
            return_value={"prompt": "test", "model": "test-model-id"},
        )

        with pytest.raises(ImgGenModelNotFoundError) as exc_info:
            await worker._generate_single_image(img_gen_job=_make_img_gen_job(mocker))  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.CONFIGURATION
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.CHANGE_MODEL
        assert exc_info.value.model_handle == "sdxl-base"
        assert exc_info.value.provider_metadata is not None
        assert exc_info.value.provider_metadata.status_code == 404

    async def test_timeout_carries_metadata(self, mocker: MockerFixture) -> None:
        worker = _make_worker(mocker)
        sdk_exc = InferenceTimeoutError("timed out")
        worker.hf_async_client.text_to_image.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        mocker.patch(
            "pipelex.plugins.huggingface.huggingface_img_gen_worker.ImgGenArgsFactory.make_args_for_model",
            new_callable=mocker.AsyncMock,
            return_value={"prompt": "test", "model": "test-model-id"},
        )

        with pytest.raises(ImgGenGenerationError) as exc_info:
            await worker._generate_single_image(img_gen_job=_make_img_gen_job(mocker))  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.TRANSIENT
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.WAIT_AND_RETRY
        assert exc_info.value.provider_metadata is not None
        assert exc_info.value.provider_metadata.sdk_exception_type == "InferenceTimeoutError"
