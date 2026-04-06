"""Tests for FAL ImgGen worker SDK exception handling and error categorization."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from fal_client.auth import MissingCredentialsError
from fal_client.client import FalClientError, FalClientHTTPError, FalClientTimeoutError

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

from pipelex.cogt.exceptions import ImgGenGenerationError, InferenceErrorCategory
from pipelex.plugins.fal.fal_img_gen_worker import FalImgGenWorker
from tests.unit.pipelex.plugins.fal.test_data import FalErrorHandlingTestData


def _make_fal_http_error(status_code: int, message: str) -> FalClientHTTPError:
    """Create a FalClientHTTPError for testing."""
    import httpx  # noqa: PLC0415

    request = httpx.Request("POST", "https://fal.ai/test")
    response = httpx.Response(status_code=status_code, request=request, text=message)
    return FalClientHTTPError(message=message, status_code=status_code, response_headers={}, response=response)


def _make_fal_timeout_error() -> FalClientTimeoutError:
    """Create a FalClientTimeoutError for testing."""
    return FalClientTimeoutError(timeout=30.0)


def _make_fal_client_error(message: str = "FAL client error") -> FalClientError:
    """Create a FalClientError for testing."""
    return FalClientError(message)


def _make_missing_credentials_error() -> MissingCredentialsError:
    """Create a minimal MissingCredentialsError for testing."""
    return MissingCredentialsError()


def _make_fal_img_gen_worker(mocker: MockerFixture) -> FalImgGenWorker:
    """Create a minimal FalImgGenWorker with mocked internals."""
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
    """Create a mock ImgGen job."""
    job = mocker.MagicMock()
    job.img_gen_prompt.positive_text = "a sunset over mountains"
    job.job_report.img_gen_tokens_usage = None
    return job


@pytest.mark.asyncio(loop_scope="class")
class TestFalWorkerErrorHandling:
    """Tests for FAL ImgGen worker SDK exception handling and error categorization."""

    @pytest.mark.parametrize(
        ("_topic", "status_code", "message", "expected_category", "expected_message_substring"),
        FalErrorHandlingTestData.HTTP_ERROR_CASES,
    )
    async def test_http_error_categorization(
        self,
        mocker: MockerFixture,
        _topic: str,
        status_code: int,
        message: str,
        expected_category: InferenceErrorCategory,
        expected_message_substring: str,
    ) -> None:
        """FalClientHTTPError is caught and categorized correctly based on status code."""
        worker = _make_fal_img_gen_worker(mocker)
        sdk_exc = _make_fal_http_error(status_code, message)
        worker.fal_async_client.submit.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        mocker.patch(
            "pipelex.plugins.fal.fal_img_gen_worker.ImgGenArgsFactory.make_args_for_model",
            new_callable=mocker.AsyncMock,
            return_value={"prompt": "test"},
        )

        with pytest.raises(ImgGenGenerationError) as exc_info:
            await worker._submit_and_get_result(img_gen_job=_make_img_gen_job(mocker), nb_images=1)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is expected_category
        assert exc_info.value.__cause__ is sdk_exc
        assert expected_message_substring in exc_info.value.args[0].lower()

    @pytest.mark.parametrize(
        ("_topic", "expected_category", "expected_message_substring"),
        FalErrorHandlingTestData.MISSING_CREDENTIALS_CASES,
    )
    async def test_missing_credentials_is_configuration(
        self,
        mocker: MockerFixture,
        _topic: str,
        expected_category: InferenceErrorCategory,
        expected_message_substring: str,
    ) -> None:
        """MissingCredentialsError is caught and categorized as CONFIGURATION."""
        worker = _make_fal_img_gen_worker(mocker)
        sdk_exc = _make_missing_credentials_error()
        worker.fal_async_client.submit.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        mocker.patch(
            "pipelex.plugins.fal.fal_img_gen_worker.ImgGenArgsFactory.make_args_for_model",
            new_callable=mocker.AsyncMock,
            return_value={"prompt": "test"},
        )

        with pytest.raises(ImgGenGenerationError) as exc_info:
            await worker._submit_and_get_result(img_gen_job=_make_img_gen_job(mocker), nb_images=1)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is expected_category
        assert exc_info.value.__cause__ is sdk_exc
        assert expected_message_substring in exc_info.value.args[0].lower()

    @pytest.mark.parametrize(
        ("_topic", "expected_category", "expected_message_substring"),
        FalErrorHandlingTestData.TIMEOUT_CASES,
    )
    async def test_timeout_error_is_transient(
        self,
        mocker: MockerFixture,
        _topic: str,
        expected_category: InferenceErrorCategory,
        expected_message_substring: str,
    ) -> None:
        """FalClientTimeoutError is caught and categorized as TRANSIENT."""
        worker = _make_fal_img_gen_worker(mocker)
        sdk_exc = _make_fal_timeout_error()
        worker.fal_async_client.submit.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        mocker.patch(
            "pipelex.plugins.fal.fal_img_gen_worker.ImgGenArgsFactory.make_args_for_model",
            new_callable=mocker.AsyncMock,
            return_value={"prompt": "test"},
        )

        with pytest.raises(ImgGenGenerationError) as exc_info:
            await worker._submit_and_get_result(img_gen_job=_make_img_gen_job(mocker), nb_images=1)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is expected_category
        assert exc_info.value.__cause__ is sdk_exc
        assert expected_message_substring in exc_info.value.args[0].lower()

    @pytest.mark.parametrize(
        ("_topic", "expected_category", "expected_message_substring"),
        FalErrorHandlingTestData.GENERIC_CLIENT_ERROR_CASES,
    )
    async def test_generic_client_error_is_transient(
        self,
        mocker: MockerFixture,
        _topic: str,
        expected_category: InferenceErrorCategory,
        expected_message_substring: str,
    ) -> None:
        """FalClientError is caught and categorized as TRANSIENT."""
        worker = _make_fal_img_gen_worker(mocker)
        sdk_exc = _make_fal_client_error()
        worker.fal_async_client.submit.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        mocker.patch(
            "pipelex.plugins.fal.fal_img_gen_worker.ImgGenArgsFactory.make_args_for_model",
            new_callable=mocker.AsyncMock,
            return_value={"prompt": "test"},
        )

        with pytest.raises(ImgGenGenerationError) as exc_info:
            await worker._submit_and_get_result(img_gen_job=_make_img_gen_job(mocker), nb_images=1)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is expected_category
        assert exc_info.value.__cause__ is sdk_exc
        assert expected_message_substring in exc_info.value.args[0].lower()

    async def test_error_report_includes_category(self, mocker: MockerFixture) -> None:
        """to_error_report() includes error_category and retryable from the exception."""
        worker = _make_fal_img_gen_worker(mocker)
        sdk_exc = _make_fal_http_error(402, "Payment required")
        worker.fal_async_client.submit.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        mocker.patch(
            "pipelex.plugins.fal.fal_img_gen_worker.ImgGenArgsFactory.make_args_for_model",
            new_callable=mocker.AsyncMock,
            return_value={"prompt": "test"},
        )

        with pytest.raises(ImgGenGenerationError) as exc_info:
            await worker._submit_and_get_result(img_gen_job=_make_img_gen_job(mocker), nb_images=1)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        report = exc_info.value.to_error_report()
        assert report.error_category == "capacity"
        assert report.retryable is False
        assert report.error_type == "ImgGenGenerationError"
