"""Tests for Azure ImgGen worker HTTP exception handling and error categorization."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx
import pytest

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

from pipelex.cogt.exceptions import ImgGenGenerationError, InferenceErrorCategory
from pipelex.plugins.azure_rest.azure_img_gen_worker import AzureImgGenWorker
from tests.unit.pipelex.plugins.azure_rest.test_data import AzureErrorHandlingTestData


def _make_httpx_status_error(status_code: int, text: str = "") -> httpx.HTTPStatusError:
    """Create a minimal httpx.HTTPStatusError for testing."""
    request = httpx.Request("POST", "https://test.azure.com/api")
    response = httpx.Response(status_code=status_code, request=request, text=text)
    return httpx.HTTPStatusError("error", request=request, response=response)


def _make_azure_img_gen_worker(mocker: MockerFixture) -> AzureImgGenWorker:
    """Create a minimal AzureImgGenWorker with mocked internals."""
    worker = object.__new__(AzureImgGenWorker)
    mock_model = mocker.MagicMock()
    mock_model.desc = "test-azure-model"
    mock_model.model_id = "dall-e-3"
    mock_model.name = "dall-e-3"
    mock_model.rules = mocker.MagicMock()
    worker.inference_model = mock_model
    worker.api_key = "test-api-key"
    worker.endpoint = "https://test.azure.com"
    worker.api_version = "2024-02-01"
    worker.plugin = mocker.MagicMock()
    return worker


def _make_img_gen_job(mocker: MockerFixture) -> Any:
    """Create a mock ImgGen job."""
    job = mocker.MagicMock()
    job.img_gen_prompt.positive_text = "a sunset over mountains"
    job.job_report.img_gen_tokens_usage = None
    return job


@pytest.mark.asyncio(loop_scope="class")
class TestAzureWorkerErrorHandling:
    """Tests for Azure ImgGen worker HTTP exception handling and error categorization."""

    @pytest.mark.parametrize(
        ("_topic", "status_code", "response_text", "expected_category", "expected_message_substring"),
        AzureErrorHandlingTestData.HTTP_STATUS_ERROR_CASES,
    )
    async def test_http_status_error_categorization(
        self,
        mocker: MockerFixture,
        _topic: str,
        status_code: int,
        response_text: str,
        expected_category: InferenceErrorCategory,
        expected_message_substring: str,
    ) -> None:
        """HTTPStatusError is caught and categorized correctly based on status code."""
        worker = _make_azure_img_gen_worker(mocker)
        sdk_exc = _make_httpx_status_error(status_code, response_text)

        mock_client = mocker.MagicMock()
        mock_response = mocker.MagicMock()
        mock_response.raise_for_status.side_effect = sdk_exc
        mock_client.__aenter__ = mocker.AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = mocker.AsyncMock(return_value=False)
        mock_client.post = mocker.AsyncMock(return_value=mock_response)

        mocker.patch("pipelex.plugins.azure_rest.azure_img_gen_worker.httpx.AsyncClient", return_value=mock_client)
        mocker.patch(
            "pipelex.plugins.azure_rest.azure_img_gen_worker.ImgGenArgsFactory.make_args_for_model",
            new_callable=mocker.AsyncMock,
            return_value={"prompt": "test"},
        )

        with pytest.raises(ImgGenGenerationError) as exc_info:
            await worker._gen_image_list(img_gen_job=_make_img_gen_job(mocker), nb_images=1)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is expected_category
        assert exc_info.value.__cause__ is sdk_exc
        assert expected_message_substring in exc_info.value.args[0].lower()

    @pytest.mark.parametrize(
        ("_topic", "expected_category", "expected_message_substring"),
        AzureErrorHandlingTestData.CONNECT_ERROR_CASES,
    )
    async def test_connect_error_is_transient(
        self,
        mocker: MockerFixture,
        _topic: str,
        expected_category: InferenceErrorCategory,
        expected_message_substring: str,
    ) -> None:
        """ConnectError is caught and categorized as TRANSIENT."""
        worker = _make_azure_img_gen_worker(mocker)
        request = httpx.Request("POST", "https://test.azure.com/api")
        sdk_exc = httpx.ConnectError("Connection refused", request=request)

        mock_client = mocker.MagicMock()
        mock_client.__aenter__ = mocker.AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = mocker.AsyncMock(return_value=False)
        mock_client.post = mocker.AsyncMock(side_effect=sdk_exc)

        mocker.patch("pipelex.plugins.azure_rest.azure_img_gen_worker.httpx.AsyncClient", return_value=mock_client)
        mocker.patch(
            "pipelex.plugins.azure_rest.azure_img_gen_worker.ImgGenArgsFactory.make_args_for_model",
            new_callable=mocker.AsyncMock,
            return_value={"prompt": "test"},
        )

        with pytest.raises(ImgGenGenerationError) as exc_info:
            await worker._gen_image_list(img_gen_job=_make_img_gen_job(mocker), nb_images=1)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is expected_category
        assert exc_info.value.__cause__ is sdk_exc
        assert expected_message_substring in exc_info.value.args[0].lower()

    @pytest.mark.parametrize(
        ("_topic", "expected_category", "expected_message_substring"),
        AzureErrorHandlingTestData.TIMEOUT_ERROR_CASES,
    )
    async def test_timeout_error_is_transient(
        self,
        mocker: MockerFixture,
        _topic: str,
        expected_category: InferenceErrorCategory,
        expected_message_substring: str,
    ) -> None:
        """TimeoutException is caught and categorized as TRANSIENT."""
        worker = _make_azure_img_gen_worker(mocker)
        sdk_exc = httpx.ReadTimeout("Request timed out")

        mock_client = mocker.MagicMock()
        mock_client.__aenter__ = mocker.AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = mocker.AsyncMock(return_value=False)
        mock_client.post = mocker.AsyncMock(side_effect=sdk_exc)

        mocker.patch("pipelex.plugins.azure_rest.azure_img_gen_worker.httpx.AsyncClient", return_value=mock_client)
        mocker.patch(
            "pipelex.plugins.azure_rest.azure_img_gen_worker.ImgGenArgsFactory.make_args_for_model",
            new_callable=mocker.AsyncMock,
            return_value={"prompt": "test"},
        )

        with pytest.raises(ImgGenGenerationError) as exc_info:
            await worker._gen_image_list(img_gen_job=_make_img_gen_job(mocker), nb_images=1)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is expected_category
        assert exc_info.value.__cause__ is sdk_exc
        assert expected_message_substring in exc_info.value.args[0].lower()

    async def test_error_report_includes_category(self, mocker: MockerFixture) -> None:
        """to_error_report() includes error_category and retryable from the exception."""
        worker = _make_azure_img_gen_worker(mocker)
        sdk_exc = _make_httpx_status_error(429, "Rate limit exceeded")

        mock_client = mocker.MagicMock()
        mock_response = mocker.MagicMock()
        mock_response.raise_for_status.side_effect = sdk_exc
        mock_client.__aenter__ = mocker.AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = mocker.AsyncMock(return_value=False)
        mock_client.post = mocker.AsyncMock(return_value=mock_response)

        mocker.patch("pipelex.plugins.azure_rest.azure_img_gen_worker.httpx.AsyncClient", return_value=mock_client)
        mocker.patch(
            "pipelex.plugins.azure_rest.azure_img_gen_worker.ImgGenArgsFactory.make_args_for_model",
            new_callable=mocker.AsyncMock,
            return_value={"prompt": "test"},
        )

        with pytest.raises(ImgGenGenerationError) as exc_info:
            await worker._gen_image_list(img_gen_job=_make_img_gen_job(mocker), nb_images=1)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        report = exc_info.value.to_error_report()
        assert report.error_category == "transient"
        assert report.retryable is True
        assert report.error_type == "ImgGenGenerationError"
