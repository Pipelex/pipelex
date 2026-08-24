"""Tests for Mistral extract worker provider_metadata + semantic UserActionKind."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx
import pytest
from mistralai import MistralError

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

from pipelex.cogt.exceptions import ExtractJobFailureError, ExtractModelNotFoundError, InferenceErrorCategory
from pipelex.cogt.inference.error_classification import UserActionKind
from pipelex.providers.mistral.mistral_extract_worker import MistralExtractWorker


def _make_mistral_error(status_code: int, message: str) -> MistralError:
    request = httpx.Request("POST", "https://api.mistral.ai/v1/ocr")
    response = httpx.Response(status_code=status_code, request=request, headers={"x-request-id": "mst-1"})
    return MistralError(message, raw_response=response)


def _make_worker(mocker: MockerFixture) -> MistralExtractWorker:
    worker = object.__new__(MistralExtractWorker)
    mock_model = mocker.MagicMock()
    mock_model.desc = "test-mistral-ocr"
    mock_model.model_id = "mistral-ocr"
    mock_model.name = "mistral-ocr"
    worker.inference_model = mock_model

    mock_client = mocker.MagicMock()
    mock_client.ocr.process_async = mocker.AsyncMock()
    worker.mistral_client = mock_client
    return worker


@pytest.mark.asyncio(loop_scope="class")
class TestMistralExtractWorkerSemantic:
    """Each MistralError branch carries semantic UserActionKind + provider_metadata."""

    @pytest.mark.parametrize(
        ("status_code", "error_message", "expected_category", "expected_kind"),
        [
            (402, "Payment required: insufficient credits", InferenceErrorCategory.CAPACITY, UserActionKind.CHECK_BILLING),
            (429, "Too many requests, quota exceeded", InferenceErrorCategory.CAPACITY, UserActionKind.CHECK_BILLING),
            (429, "Rate limit exceeded", InferenceErrorCategory.TRANSIENT, UserActionKind.WAIT_AND_RETRY),
            (401, "Invalid API key", InferenceErrorCategory.CONFIGURATION, UserActionKind.CHECK_CREDENTIALS),
            (403, "Forbidden", InferenceErrorCategory.CONFIGURATION, UserActionKind.CHECK_CREDENTIALS),
            # NOTE: a 404 is not in this parametrized set — the Extract worker specializes
            # it to ExtractModelNotFoundError, covered by its own dedicated test.
            (400, "Request blocked by content_policy", InferenceErrorCategory.CONTENT, UserActionKind.CHANGE_INPUT),
            (400, "Invalid request", InferenceErrorCategory.CONTENT, UserActionKind.CHANGE_INPUT),
            (500, "Server error", InferenceErrorCategory.TRANSIENT, UserActionKind.WAIT_AND_RETRY),
            # Unrecognized 4xx (e.g. 418) classifies as non-retryable CONFIGURATION via the unified ladder.
            (418, "I'm a teapot", InferenceErrorCategory.CONFIGURATION, UserActionKind.CHANGE_INPUT),
        ],
    )
    async def test_mistral_error_carries_semantic_user_action(
        self,
        mocker: MockerFixture,
        status_code: int,
        error_message: str,
        expected_category: InferenceErrorCategory,
        expected_kind: UserActionKind,
    ) -> None:
        worker = _make_worker(mocker)
        sdk_exc = _make_mistral_error(status_code, error_message)
        cast_client: Any = worker.mistral_client
        cast_client.ocr.process_async.side_effect = sdk_exc

        mocker.patch(
            "pipelex.providers.mistral.mistral_extract_worker.MistralFactory.make_mistral_image_url_chunk_from_uri",
            return_value={"type": "image_url", "image_url": "https://example.com/test.png"},
        )

        with pytest.raises(ExtractJobFailureError) as exc_info:
            await worker._extract_page_from_image(image_uri="https://example.com/test.png")  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is expected_category
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is expected_kind
        assert exc_info.value.provider_metadata is not None
        assert exc_info.value.provider_metadata.provider == "mistral"
        assert exc_info.value.provider_metadata.sdk_exception_type == "MistralError"
        assert exc_info.value.provider_metadata.status_code == status_code
        assert exc_info.value.__cause__ is sdk_exc

    @pytest.mark.parametrize(
        ("exc_class", "expected_sdk_type"),
        [
            (httpx.ConnectError, "ConnectError"),
            (httpx.ConnectTimeout, "ConnectTimeout"),
            (httpx.ReadError, "TransportError"),
            (httpx.RemoteProtocolError, "TransportError"),
        ],
    )
    async def test_httpx_transport_error_image_path_is_wrapped_as_transient(
        self,
        mocker: MockerFixture,
        exc_class: type[httpx.TransportError],
        expected_sdk_type: str,
    ) -> None:
        """A direct httpx.TransportError on the image OCR path must surface as TRANSIENT
        ExtractJobFailureError, matching the Mistral LLM worker's transport-error handling.
        """
        worker = _make_worker(mocker)
        request = httpx.Request("POST", "https://api.mistral.ai/v1/ocr")
        sdk_exc = exc_class("transport failure", request=request)
        cast_client: Any = worker.mistral_client
        cast_client.ocr.process_async.side_effect = sdk_exc

        mocker.patch(
            "pipelex.providers.mistral.mistral_extract_worker.MistralFactory.make_mistral_image_url_chunk_from_uri",
            return_value={"type": "image_url", "image_url": "https://example.com/test.png"},
        )

        with pytest.raises(ExtractJobFailureError) as exc_info:
            await worker._extract_page_from_image(image_uri="https://example.com/test.png")  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.TRANSIENT
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.WAIT_AND_RETRY
        assert exc_info.value.provider_metadata is not None
        assert exc_info.value.provider_metadata.provider == "mistral"
        assert exc_info.value.provider_metadata.status_code is None
        assert exc_info.value.provider_metadata.sdk_exception_type == expected_sdk_type
        assert exc_info.value.__cause__ is sdk_exc

    async def test_httpx_transport_error_document_path_is_wrapped_as_transient(
        self,
        mocker: MockerFixture,
    ) -> None:
        """The document OCR path must also catch httpx.TransportError. Without this, a
        statusless transport failure escapes raw and bypasses the Extract/Classify/Render
        pipeline.
        """
        worker = _make_worker(mocker)
        request = httpx.Request("POST", "https://api.mistral.ai/v1/ocr")
        sdk_exc = httpx.ReadError("connection reset", request=request)
        cast_client: Any = worker.mistral_client
        cast_client.ocr.process_async.side_effect = sdk_exc

        mocker.patch(
            "pipelex.providers.mistral.mistral_extract_worker.MistralFactory.make_mistral_document_url_chunk_from_uri",
            return_value={"type": "document_url", "document_url": "https://example.com/doc.pdf"},
        )

        extract_job_params = mocker.MagicMock()
        extract_job_params.should_caption_images = False
        extract_job_params.max_nb_images = None
        extract_job_params.image_min_size = None

        with pytest.raises(ExtractJobFailureError) as exc_info:
            await worker._extract_pages_from_document(  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]
                document_uri="https://example.com/doc.pdf",
                extract_job_params=extract_job_params,
            )

        assert exc_info.value.error_category is InferenceErrorCategory.TRANSIENT
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.WAIT_AND_RETRY
        assert exc_info.value.provider_metadata is not None
        assert exc_info.value.provider_metadata.provider == "mistral"
        assert exc_info.value.provider_metadata.status_code is None
        assert exc_info.value.provider_metadata.sdk_exception_type == "TransportError"
        assert exc_info.value.__cause__ is sdk_exc

    async def test_mistral_404_raises_extract_model_not_found_error(self, mocker: MockerFixture) -> None:
        """A 404 MistralError specializes to ExtractModelNotFoundError on the Extract path."""
        worker = _make_worker(mocker)
        sdk_exc = _make_mistral_error(404, "Model not found")
        cast_client: Any = worker.mistral_client
        cast_client.ocr.process_async.side_effect = sdk_exc

        mocker.patch(
            "pipelex.providers.mistral.mistral_extract_worker.MistralFactory.make_mistral_image_url_chunk_from_uri",
            return_value={"type": "image_url", "image_url": "https://example.com/test.png"},
        )

        with pytest.raises(ExtractModelNotFoundError) as exc_info:
            await worker._extract_page_from_image(image_uri="https://example.com/test.png")  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.CONFIGURATION
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.CHANGE_MODEL
        assert exc_info.value.provider_metadata is not None
        assert exc_info.value.provider_metadata.provider == "mistral"
        assert exc_info.value.provider_metadata.status_code == 404
        assert exc_info.value.__cause__ is sdk_exc
