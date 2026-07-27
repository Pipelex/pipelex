"""Tests for Google ImgGen worker provider_metadata + semantic UserActionKind values.

The existing ``test_google_worker_error_handling.py`` covers categorization on both
LLM and ImgGen workers. This module adds the upgrade-A/B/C assertions for the
ImgGen worker specifically: provider_metadata population + semantic UserActionKind.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx
import pytest
from google.genai import errors as genai_errors

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

from pipelex.cogt.exceptions import ImgGenGenerationError, ImgGenModelNotFoundError, InferenceErrorCategory
from pipelex.cogt.img_gen.img_gen_model_rules import AspectRatioTaxonomy, ImgGenArgTopic
from pipelex.cogt.inference.error_classification import UserActionKind
from pipelex.providers.google.google_img_gen_factory import ResolvedGoogleImageConfig
from pipelex.providers.google.google_img_gen_worker import GoogleImgGenWorker


def _make_google_client_error(code: int, message: str, status: str = "ERROR") -> genai_errors.ClientError:
    response_json = {"message": message, "status": status, "error": {"status": status, "code": code, "message": message}}
    return genai_errors.ClientError(code, response_json, None)


def _make_google_server_error(code: int, message: str) -> genai_errors.ServerError:
    response_json = {"message": message, "status": "INTERNAL"}
    return genai_errors.ServerError(code, response_json, None)


def _make_worker(mocker: MockerFixture) -> GoogleImgGenWorker:
    worker = object.__new__(GoogleImgGenWorker)
    mock_model = mocker.MagicMock()
    mock_model.desc = "test-model-desc"
    mock_model.model_id = "imagen-3.0-generate-002"
    mock_model.name = "imagen-3.0-generate-002"
    mock_model.rules = {ImgGenArgTopic.ASPECT_RATIO: AspectRatioTaxonomy.GEMINI_3_FLASH}
    worker.inference_model = mock_model

    mock_async_client = mocker.MagicMock()
    mock_async_client.models.generate_content = mocker.AsyncMock()
    worker.genai_async_client = mock_async_client

    mocker.patch(
        "pipelex.providers.google.google_img_gen_worker.GoogleImgGenFactory.resolve_image_config",
        return_value=ResolvedGoogleImageConfig(aspect_ratio="1:1", image_size=None, width=1024, height=1024),
    )
    return worker


def _make_img_gen_job(mocker: MockerFixture) -> Any:
    job = mocker.MagicMock()
    job.job_params.aspect_ratio = None
    job.job_params.output_format = None
    job.img_gen_prompt.positive_text = "a cute cat"
    job.job_report.img_gen_tokens_usage = None
    return job


@pytest.mark.asyncio(loop_scope="class")
class TestGoogleImgGenWorkerErrorHandling:
    """Asserts metadata + user_action.kind for every classification branch."""

    async def test_not_found_404_is_change_model_with_metadata(self, mocker: MockerFixture) -> None:
        worker = _make_worker(mocker)
        sdk_exc = _make_google_client_error(404, "Model gemini-99 not found", status="NOT_FOUND")
        worker.genai_async_client.models.generate_content.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(ImgGenModelNotFoundError) as exc_info:
            await worker._gen_image(img_gen_job=_make_img_gen_job(mocker))  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.CONFIGURATION
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.CHANGE_MODEL
        assert exc_info.value.model_handle == "imagen-3.0-generate-002"
        assert exc_info.value.provider_metadata is not None
        assert exc_info.value.provider_metadata.status_code == 404
        assert exc_info.value.provider_metadata.provider == "google"

    async def test_auth_401_is_check_credentials(self, mocker: MockerFixture) -> None:
        worker = _make_worker(mocker)
        sdk_exc = _make_google_client_error(401, "Invalid credentials", status="UNAUTHENTICATED")
        worker.genai_async_client.models.generate_content.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(ImgGenGenerationError) as exc_info:
            await worker._gen_image(img_gen_job=_make_img_gen_job(mocker))  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.CONFIGURATION
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.CHECK_CREDENTIALS
        assert exc_info.value.provider_metadata is not None
        assert exc_info.value.provider_metadata.status_code == 401

    async def test_forbidden_403_is_check_credentials(self, mocker: MockerFixture) -> None:
        worker = _make_worker(mocker)
        sdk_exc = _make_google_client_error(403, "Permission denied", status="PERMISSION_DENIED")
        worker.genai_async_client.models.generate_content.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(ImgGenGenerationError) as exc_info:
            await worker._gen_image(img_gen_job=_make_img_gen_job(mocker))  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.CONFIGURATION
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.CHECK_CREDENTIALS

    async def test_quota_429_is_check_billing(self, mocker: MockerFixture) -> None:
        worker = _make_worker(mocker)
        sdk_exc = _make_google_client_error(429, "Resource has been exhausted (e.g. check quota)", status="RESOURCE_EXHAUSTED")
        worker.genai_async_client.models.generate_content.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(ImgGenGenerationError) as exc_info:
            await worker._gen_image(img_gen_job=_make_img_gen_job(mocker))  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.CAPACITY
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.CHECK_BILLING

    async def test_generic_rate_limit_429_is_wait_and_retry(self, mocker: MockerFixture) -> None:
        worker = _make_worker(mocker)
        sdk_exc = _make_google_client_error(429, "Too many requests, please slow down")
        worker.genai_async_client.models.generate_content.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(ImgGenGenerationError) as exc_info:
            await worker._gen_image(img_gen_job=_make_img_gen_job(mocker))  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.TRANSIENT
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.WAIT_AND_RETRY

    async def test_content_policy_400_is_change_input(self, mocker: MockerFixture) -> None:
        worker = _make_worker(mocker)
        sdk_exc = _make_google_client_error(400, "Your request was rejected due to content_policy_violation")
        worker.genai_async_client.models.generate_content.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(ImgGenGenerationError) as exc_info:
            await worker._gen_image(img_gen_job=_make_img_gen_job(mocker))  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.CONTENT
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.CHANGE_INPUT

    async def test_generic_400_is_change_input(self, mocker: MockerFixture) -> None:
        worker = _make_worker(mocker)
        sdk_exc = _make_google_client_error(400, "Invalid parameter: temperature must be between 0 and 2")
        worker.genai_async_client.models.generate_content.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(ImgGenGenerationError) as exc_info:
            await worker._gen_image(img_gen_job=_make_img_gen_job(mocker))  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.CONTENT
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.CHANGE_INPUT

    async def test_unhandled_4xx_is_change_input(self, mocker: MockerFixture) -> None:
        """A ClientError with an unhandled 4xx status is non-retryable CONFIGURATION, not TRANSIENT."""
        worker = _make_worker(mocker)
        sdk_exc = _make_google_client_error(409, "Conflict: resource already exists")
        worker.genai_async_client.models.generate_content.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(ImgGenGenerationError) as exc_info:
            await worker._gen_image(img_gen_job=_make_img_gen_job(mocker))  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.CONFIGURATION
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.CHANGE_INPUT

    async def test_server_error_500_is_wait_and_retry(self, mocker: MockerFixture) -> None:
        worker = _make_worker(mocker)
        sdk_exc = _make_google_server_error(500, "Internal server error")
        worker.genai_async_client.models.generate_content.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(ImgGenGenerationError) as exc_info:
            await worker._gen_image(img_gen_job=_make_img_gen_job(mocker))  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.TRANSIENT
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.WAIT_AND_RETRY
        assert exc_info.value.provider_metadata is not None
        assert exc_info.value.provider_metadata.status_code == 500

    @pytest.mark.parametrize(
        ("exc_class", "expected_sdk_type"),
        [
            (httpx.ConnectError, "ConnectError"),
            (httpx.ConnectTimeout, "ConnectTimeout"),
            (httpx.ReadError, "TransportError"),
            (httpx.RemoteProtocolError, "TransportError"),
        ],
    )
    async def test_httpx_transport_error_is_wrapped_as_transient(
        self,
        mocker: MockerFixture,
        exc_class: type[httpx.TransportError],
        expected_sdk_type: str,
    ) -> None:
        """A direct httpx.TransportError from generate_content() must be caught and routed through
        the categorizer as a TRANSIENT ImgGenGenerationError, matching the Google LLM worker.
        """
        worker = _make_worker(mocker)
        request = httpx.Request("POST", "https://generativelanguage.googleapis.com/v1/models/imagen-3.0-generate-002:generateContent")
        sdk_exc = exc_class("transport failure", request=request)
        worker.genai_async_client.models.generate_content.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(ImgGenGenerationError) as exc_info:
            await worker._gen_image(img_gen_job=_make_img_gen_job(mocker))  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.TRANSIENT
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.WAIT_AND_RETRY
        assert exc_info.value.provider_metadata is not None
        assert exc_info.value.provider_metadata.provider == "google"
        assert exc_info.value.provider_metadata.status_code is None
        assert exc_info.value.provider_metadata.sdk_exception_type == expected_sdk_type
        assert exc_info.value.__cause__ is sdk_exc

    async def test_to_error_report_serializes_metadata(self, mocker: MockerFixture) -> None:
        worker = _make_worker(mocker)
        sdk_exc = _make_google_client_error(429, "Resource has been exhausted", status="RESOURCE_EXHAUSTED")
        worker.genai_async_client.models.generate_content.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(ImgGenGenerationError) as exc_info:
            await worker._gen_image(img_gen_job=_make_img_gen_job(mocker))  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        report = exc_info.value.to_error_report()
        assert report.error_category == "capacity"
        assert report.retryable is False
        assert report.provider_metadata is not None
        assert report.provider_metadata.provider == "google"
        assert report.provider_metadata.status_code == 429
