"""Tests for Azure ImgGen worker provider_metadata + semantic UserActionKind values.

The existing ``test_azure_worker_error_handling.py`` covers categorization
through ``error_category``; this module asserts the upgrade-A/B/C contract
(provider_metadata + ``user_action.kind``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx
import pytest

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

from pipelex.cogt.exceptions import ImgGenGenerationError, InferenceErrorCategory
from pipelex.cogt.inference.error_classification import UserActionKind
from pipelex.plugins.azure_rest.azure_img_gen_worker import AzureImgGenWorker


def _make_status_error(status_code: int, text: str = "", headers: dict[str, str] | None = None) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "https://test.azure.com/api")
    response = httpx.Response(status_code=status_code, request=request, text=text, headers=headers or {})
    return httpx.HTTPStatusError("error", request=request, response=response)


def _make_worker(mocker: MockerFixture) -> AzureImgGenWorker:
    worker = object.__new__(AzureImgGenWorker)
    mock_model = mocker.MagicMock()
    mock_model.desc = "test-azure-model"
    mock_model.model_id = "dall-e-3"
    mock_model.name = "dall-e-3"
    mock_model.rules = mocker.MagicMock()
    worker.inference_model = mock_model
    worker.api_key = "test-key"
    worker.endpoint = "https://test.azure.com"
    worker.api_version = "2024-02-01"
    worker.plugin = mocker.MagicMock()
    return worker


def _make_img_gen_job(mocker: MockerFixture) -> Any:
    job = mocker.MagicMock()
    job.img_gen_prompt.positive_text = "a sunset over mountains"
    job.job_report.img_gen_tokens_usage = None
    return job


def _patch_httpx_status_error(mocker: MockerFixture, sdk_exc: httpx.HTTPStatusError) -> None:
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


@pytest.mark.asyncio(loop_scope="class")
class TestAzureImgGenWorkerSemantic:
    """Each branch carries semantic UserActionKind + provider_metadata."""

    async def test_rate_limit_429_is_wait_and_retry_with_metadata(self, mocker: MockerFixture) -> None:
        worker = _make_worker(mocker)
        sdk_exc = _make_status_error(429, text="rate limited", headers={"x-ms-request-id": "req-1"})
        _patch_httpx_status_error(mocker, sdk_exc)

        with pytest.raises(ImgGenGenerationError) as exc_info:
            await worker._gen_image_list(img_gen_job=_make_img_gen_job(mocker), nb_images=1)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.TRANSIENT
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.WAIT_AND_RETRY
        assert exc_info.value.provider_metadata is not None
        assert exc_info.value.provider_metadata.provider == "azure"
        assert exc_info.value.provider_metadata.status_code == 429
        assert exc_info.value.provider_metadata.request_id == "req-1"

    async def test_quota_402_is_check_billing(self, mocker: MockerFixture) -> None:
        worker = _make_worker(mocker)
        sdk_exc = _make_status_error(402, text="payment required")
        _patch_httpx_status_error(mocker, sdk_exc)

        with pytest.raises(ImgGenGenerationError) as exc_info:
            await worker._gen_image_list(img_gen_job=_make_img_gen_job(mocker), nb_images=1)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.CAPACITY
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.CHECK_BILLING

    async def test_auth_401_is_check_credentials(self, mocker: MockerFixture) -> None:
        worker = _make_worker(mocker)
        sdk_exc = _make_status_error(401, text="invalid key")
        _patch_httpx_status_error(mocker, sdk_exc)

        with pytest.raises(ImgGenGenerationError) as exc_info:
            await worker._gen_image_list(img_gen_job=_make_img_gen_job(mocker), nb_images=1)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.CONFIGURATION
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.CHECK_CREDENTIALS

    async def test_not_found_404_is_change_model(self, mocker: MockerFixture) -> None:
        worker = _make_worker(mocker)
        sdk_exc = _make_status_error(404, text="deployment not found")
        _patch_httpx_status_error(mocker, sdk_exc)

        with pytest.raises(ImgGenGenerationError) as exc_info:
            await worker._gen_image_list(img_gen_job=_make_img_gen_job(mocker), nb_images=1)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.CONFIGURATION
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.CHANGE_MODEL

    async def test_content_policy_400_is_change_input(self, mocker: MockerFixture) -> None:
        worker = _make_worker(mocker)
        sdk_exc = _make_status_error(400, text="rejected by content_policy")
        _patch_httpx_status_error(mocker, sdk_exc)

        with pytest.raises(ImgGenGenerationError) as exc_info:
            await worker._gen_image_list(img_gen_job=_make_img_gen_job(mocker), nb_images=1)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.CONTENT
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.CHANGE_INPUT

    async def test_generic_400_is_change_input(self, mocker: MockerFixture) -> None:
        worker = _make_worker(mocker)
        sdk_exc = _make_status_error(400, text="invalid parameter")
        _patch_httpx_status_error(mocker, sdk_exc)

        with pytest.raises(ImgGenGenerationError) as exc_info:
            await worker._gen_image_list(img_gen_job=_make_img_gen_job(mocker), nb_images=1)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.CONTENT
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.CHANGE_INPUT

    async def test_server_error_500_is_wait_and_retry(self, mocker: MockerFixture) -> None:
        worker = _make_worker(mocker)
        sdk_exc = _make_status_error(500, text="server error")
        _patch_httpx_status_error(mocker, sdk_exc)

        with pytest.raises(ImgGenGenerationError) as exc_info:
            await worker._gen_image_list(img_gen_job=_make_img_gen_job(mocker), nb_images=1)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.TRANSIENT
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.WAIT_AND_RETRY

    async def test_raw_response_body_excluded_from_message(self, mocker: MockerFixture) -> None:
        """The raw Azure response body must not leak into the exception message; it stays only on provider_metadata.body."""
        worker = _make_worker(mocker)
        secret_body = "SENSITIVE-DEPLOYMENT-SECRET-xyz789"
        sdk_exc = _make_status_error(429, text=secret_body)
        _patch_httpx_status_error(mocker, sdk_exc)

        with pytest.raises(ImgGenGenerationError) as exc_info:
            await worker._gen_image_list(img_gen_job=_make_img_gen_job(mocker), nb_images=1)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert secret_body not in exc_info.value.message
        assert secret_body not in str(exc_info.value)
        metadata = exc_info.value.provider_metadata
        assert metadata is not None
        assert metadata.body == secret_body

    async def test_connect_error_is_wait_and_retry(self, mocker: MockerFixture) -> None:
        worker = _make_worker(mocker)
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

        assert exc_info.value.error_category is InferenceErrorCategory.TRANSIENT
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.WAIT_AND_RETRY
        assert exc_info.value.provider_metadata is not None
        assert exc_info.value.provider_metadata.sdk_exception_type == "ConnectError"

    async def test_read_error_is_wait_and_retry(self, mocker: MockerFixture) -> None:
        """A mid-request httpx.ReadError (a TransportError subclass not covered by the connect/timeout
        handlers) must still be wrapped in ImgGenGenerationError, not escape as a raw httpx exception.
        """
        worker = _make_worker(mocker)
        request = httpx.Request("POST", "https://test.azure.com/api")
        sdk_exc = httpx.ReadError("Connection reset while reading the response", request=request)

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

        assert exc_info.value.error_category is InferenceErrorCategory.TRANSIENT
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.WAIT_AND_RETRY
        assert exc_info.value.provider_metadata is not None
        assert exc_info.value.provider_metadata.sdk_exception_type == "ReadError"
