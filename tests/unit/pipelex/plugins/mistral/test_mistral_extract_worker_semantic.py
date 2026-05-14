"""Tests for Mistral extract worker provider_metadata + semantic UserActionKind."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx
import pytest
from mistralai import MistralError

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

from pipelex.cogt.exceptions import ExtractJobFailureError, InferenceErrorCategory
from pipelex.cogt.inference.error_classification import UserActionKind
from pipelex.plugins.mistral.mistral_extract_worker import MistralExtractWorker


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
            (404, "Model not found", InferenceErrorCategory.CONFIGURATION, UserActionKind.CHANGE_MODEL),
            (400, "Request blocked by content_policy", InferenceErrorCategory.CONTENT, UserActionKind.CHANGE_INPUT),
            (400, "Invalid request", InferenceErrorCategory.CONTENT, UserActionKind.CHANGE_INPUT),
            (500, "Server error", InferenceErrorCategory.TRANSIENT, UserActionKind.WAIT_AND_RETRY),
            (418, "I'm a teapot", InferenceErrorCategory.TRANSIENT, UserActionKind.WAIT_AND_RETRY),
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
            "pipelex.plugins.mistral.mistral_extract_worker.MistralFactory.make_mistral_image_url_chunk_from_uri",
            return_value={"type": "image_url", "image_url": "https://example.com/test.png"},
        )

        with pytest.raises(ExtractJobFailureError) as exc_info:
            await worker._extract_page_from_image(image_uri="https://example.com/test.png")  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is expected_category
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is expected_kind
        assert exc_info.value.provider_metadata is not None
        assert exc_info.value.provider_metadata.provider == "mistral"
        assert exc_info.value.provider_metadata.sdk_exception_type == "MistralError"
        assert exc_info.value.provider_metadata.status_code == status_code
        assert exc_info.value.__cause__ is sdk_exc
