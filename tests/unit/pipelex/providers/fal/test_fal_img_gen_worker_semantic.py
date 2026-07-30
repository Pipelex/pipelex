"""Tests asserting provider_metadata + semantic UserActionKind on FAL ImgGen errors."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx
import pytest
from fal_client.client import FalClientError, FalClientHTTPError, FalClientTimeoutError

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

from pipelex.cogt.exceptions import ImgGenGenerationError, ImgGenModelNotFoundError, InferenceErrorCategory
from pipelex.cogt.inference.error_classification import UserActionKind
from pipelex.providers.fal.fal_img_gen_worker import FalImgGenWorker


def _make_fal_http_error(status_code: int, message: str = "") -> FalClientHTTPError:
    request = httpx.Request("POST", "https://fal.ai/test")
    response = httpx.Response(status_code=status_code, request=request, text=message)
    return FalClientHTTPError(message=message, status_code=status_code, response_headers={}, response=response)


def _make_worker(mocker: MockerFixture) -> FalImgGenWorker:
    worker = object.__new__(FalImgGenWorker)
    mock_model = mocker.MagicMock()
    mock_model.desc = "test-fal-model"
    mock_model.model_id = "fal-ai/flux/dev"
    mock_model.name = "flux-dev"
    mock_model.rules = mocker.MagicMock()
    worker.inference_model = mock_model

    mock_client = mocker.MagicMock()
    mock_client.submit = mocker.AsyncMock()
    worker.fal_async_client = mock_client
    return worker


def _make_img_gen_job(mocker: MockerFixture) -> Any:
    job = mocker.MagicMock()
    job.img_gen_prompt.positive_text = "test prompt"
    job.job_report.img_gen_tokens_usage = None
    return job


@pytest.mark.asyncio(loop_scope="class")
class TestFalImgGenWorkerSemantic:
    """Each branch carries semantic UserActionKind + provider_metadata."""

    @pytest.mark.parametrize(
        ("status_code", "expected_category", "expected_kind"),
        [
            (402, InferenceErrorCategory.CAPACITY, UserActionKind.CHECK_BILLING),
            (429, InferenceErrorCategory.TRANSIENT, UserActionKind.WAIT_AND_RETRY),
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
        sdk_exc = _make_fal_http_error(status_code, message=f"http {status_code}")
        worker.fal_async_client.submit.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        mocker.patch(
            "pipelex.providers.fal.fal_img_gen_worker.ImgGenArgsFactory.make_args_for_model",
            new_callable=mocker.AsyncMock,
            return_value={"prompt": "test", "model": "test-model-id"},
        )

        with pytest.raises(ImgGenGenerationError) as exc_info:
            await worker._submit_and_get_result(img_gen_job=_make_img_gen_job(mocker), nb_images=1)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is expected_category
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is expected_kind
        assert exc_info.value.provider_metadata is not None
        assert exc_info.value.provider_metadata.provider == "fal"
        assert exc_info.value.provider_metadata.status_code == status_code

    async def test_not_found_404_raises_img_gen_model_not_found_error(self, mocker: MockerFixture) -> None:
        """A 404 specializes to ImgGenModelNotFoundError (CONFIGURATION, CHANGE_MODEL)."""
        worker = _make_worker(mocker)
        sdk_exc = _make_fal_http_error(404, message="model not found")
        worker.fal_async_client.submit.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        mocker.patch(
            "pipelex.providers.fal.fal_img_gen_worker.ImgGenArgsFactory.make_args_for_model",
            new_callable=mocker.AsyncMock,
            return_value={"prompt": "test", "model": "test-model-id"},
        )

        with pytest.raises(ImgGenModelNotFoundError) as exc_info:
            await worker._submit_and_get_result(img_gen_job=_make_img_gen_job(mocker), nb_images=1)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.CONFIGURATION
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.CHANGE_MODEL
        assert exc_info.value.model_handle == "flux-dev"
        assert exc_info.value.provider_metadata is not None
        assert exc_info.value.provider_metadata.status_code == 404

    async def test_timeout_carries_metadata(self, mocker: MockerFixture) -> None:
        worker = _make_worker(mocker)
        sdk_exc = FalClientTimeoutError(timeout=30.0)
        worker.fal_async_client.submit.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        mocker.patch(
            "pipelex.providers.fal.fal_img_gen_worker.ImgGenArgsFactory.make_args_for_model",
            new_callable=mocker.AsyncMock,
            return_value={"prompt": "test", "model": "test-model-id"},
        )

        with pytest.raises(ImgGenGenerationError) as exc_info:
            await worker._submit_and_get_result(img_gen_job=_make_img_gen_job(mocker), nb_images=1)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.TRANSIENT
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.WAIT_AND_RETRY
        assert exc_info.value.provider_metadata is not None
        assert exc_info.value.provider_metadata.sdk_exception_type == "FalClientTimeoutError"

    async def test_generic_fal_error_carries_metadata(self, mocker: MockerFixture) -> None:
        worker = _make_worker(mocker)
        sdk_exc = FalClientError("transient fal error")
        worker.fal_async_client.submit.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        mocker.patch(
            "pipelex.providers.fal.fal_img_gen_worker.ImgGenArgsFactory.make_args_for_model",
            new_callable=mocker.AsyncMock,
            return_value={"prompt": "test", "model": "test-model-id"},
        )

        with pytest.raises(ImgGenGenerationError) as exc_info:
            await worker._submit_and_get_result(img_gen_job=_make_img_gen_job(mocker), nb_images=1)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.TRANSIENT
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.WAIT_AND_RETRY
        assert exc_info.value.provider_metadata is not None
        assert exc_info.value.provider_metadata.sdk_exception_type == "FalClientError"
