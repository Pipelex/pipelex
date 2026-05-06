"""Tests for Mistral worker SDK exception handling and error categorization."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx
import pytest
from mistralai.client.errors import MistralError

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

from pipelex.cogt.exceptions import (
    ExtractJobFailureError,
    InferenceErrorCategory,
    LLMCompletionError,
)
from pipelex.plugins.mistral.mistral_extract_worker import MistralExtractWorker
from pipelex.plugins.mistral.mistral_llm_worker import MistralLLMWorker
from tests.unit.pipelex.plugins.mistral.test_data import (
    MistralExtractErrorHandlingTestData,
    MistralLLMErrorHandlingTestData,
)


def _mock_httpx_response(status_code: int) -> httpx.Response:
    """Create a minimal httpx.Response for constructing MistralError."""
    request = httpx.Request("POST", "https://api.mistral.ai/v1/test")
    return httpx.Response(status_code=status_code, request=request)


def _make_mistral_error(status_code: int, message: str) -> MistralError:
    """Create a MistralError with the given status code and message."""
    return MistralError(message, raw_response=_mock_httpx_response(status_code))


def _make_mistral_llm_worker(mocker: MockerFixture) -> MistralLLMWorker:
    """Create a minimal MistralLLMWorker with mocked internals."""
    worker = object.__new__(MistralLLMWorker)
    mock_model = mocker.MagicMock()
    mock_model.desc = "test-model-desc"
    mock_model.model_id = "mistral-large"
    mock_model.name = "mistral-large"
    mock_model.thinking_mode = None
    mock_model.max_tokens = 4096
    worker.inference_model = mock_model
    worker.default_max_tokens = 4096

    mock_client = mocker.MagicMock()
    mock_client.chat.complete_async = mocker.AsyncMock()
    worker.mistral_client_for_text = mock_client

    mock_factory = mocker.MagicMock()
    mock_factory.make_simple_messages = mocker.AsyncMock(return_value=[])
    worker.mistral_factory = mock_factory

    return worker


def _make_mistral_extract_worker(mocker: MockerFixture) -> MistralExtractWorker:
    """Create a minimal MistralExtractWorker with mocked internals."""
    worker = object.__new__(MistralExtractWorker)
    mock_model = mocker.MagicMock()
    mock_model.desc = "test-model-desc"
    mock_model.model_id = "mistral-ocr"
    mock_model.name = "mistral-ocr"
    worker.inference_model = mock_model

    mock_client = mocker.MagicMock()
    mock_client.ocr.process_async = mocker.AsyncMock()
    worker.mistral_client = mock_client

    return worker


def _make_llm_job(mocker: MockerFixture) -> Any:
    """Create a mock LLM job."""
    job = mocker.MagicMock()
    job.applied_job_params = None
    job.job_params.temperature = 0.5
    job.job_params.max_tokens = None
    job.job_params.seed = None
    job.job_params.reasoning_effort = None
    job.job_params.reasoning_budget = None
    job.job_report.llm_tokens_usage = None
    job.llm_prompt.system_text = "system"
    return job


@pytest.mark.asyncio(loop_scope="class")
class TestMistralWorkerErrorHandling:
    """Tests for Mistral worker SDK exception handling and error categorization."""

    # ---- MistralLLMWorker error handling ----

    @pytest.mark.parametrize(
        ("_topic", "status_code", "error_message", "expected_category", "expected_action_substring"),
        MistralLLMErrorHandlingTestData.SDK_ERROR_CASES,
    )
    async def test_llm_worker_error_classification(
        self,
        mocker: MockerFixture,
        _topic: str,
        status_code: int,
        error_message: str,
        expected_category: InferenceErrorCategory,
        expected_action_substring: str | None,
    ) -> None:
        """MistralError is caught and categorized correctly by the LLM worker."""
        worker = _make_mistral_llm_worker(mocker)
        sdk_exc = _make_mistral_error(status_code, error_message)
        worker.mistral_client_for_text.chat.complete_async.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(LLMCompletionError) as exc_info:
            await worker._gen_text(llm_job=_make_llm_job(mocker))  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is expected_category
        assert exc_info.value.__cause__ is sdk_exc
        if expected_action_substring:
            assert exc_info.value.user_action is not None
            assert expected_action_substring in exc_info.value.user_action.lower()

    # ---- MistralExtractWorker error handling ----

    @pytest.mark.parametrize(
        ("_topic", "status_code", "error_message", "expected_category", "expected_action_substring"),
        MistralExtractErrorHandlingTestData.SDK_ERROR_CASES,
    )
    async def test_extract_worker_error_classification(
        self,
        mocker: MockerFixture,
        _topic: str,
        status_code: int,
        error_message: str,
        expected_category: InferenceErrorCategory,
        expected_action_substring: str | None,
    ) -> None:
        """MistralError is caught and categorized correctly by the Extract worker."""
        worker = _make_mistral_extract_worker(mocker)
        sdk_exc = _make_mistral_error(status_code, error_message)
        worker.mistral_client.ocr.process_async.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        # Patch the static factory method that runs before the API call
        mocker.patch(
            "pipelex.plugins.mistral.mistral_extract_worker.MistralFactory.make_mistral_image_url_chunk_from_uri",
            return_value={"type": "image_url", "image_url": "https://example.com/test.png"},
        )

        with pytest.raises(ExtractJobFailureError) as exc_info:
            await worker._extract_page_from_image(image_uri="https://example.com/test.png")  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is expected_category
        assert exc_info.value.__cause__ is sdk_exc
        if expected_action_substring:
            assert exc_info.value.user_action is not None
            assert expected_action_substring in exc_info.value.user_action.lower()

    # ---- to_error_report() integration ----

    async def test_llm_error_report_transient_is_retryable(self, mocker: MockerFixture) -> None:
        """to_error_report() for TRANSIENT LLM errors has retryable=True."""
        worker = _make_mistral_llm_worker(mocker)
        sdk_exc = _make_mistral_error(429, "Rate limit exceeded")
        worker.mistral_client_for_text.chat.complete_async.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(LLMCompletionError) as exc_info:
            await worker._gen_text(llm_job=_make_llm_job(mocker))  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        report = exc_info.value.to_error_report()
        assert report.error_category == "transient"
        assert report.retryable is True
        assert report.error_type == "LLMCompletionError"

    async def test_llm_error_report_capacity_not_retryable(self, mocker: MockerFixture) -> None:
        """to_error_report() for CAPACITY LLM errors has retryable=False."""
        worker = _make_mistral_llm_worker(mocker)
        sdk_exc = _make_mistral_error(402, "Payment required: insufficient credits")
        worker.mistral_client_for_text.chat.complete_async.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(LLMCompletionError) as exc_info:
            await worker._gen_text(llm_job=_make_llm_job(mocker))  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        report = exc_info.value.to_error_report()
        assert report.error_category == "capacity"
        assert report.retryable is False

    async def test_extract_error_report_includes_category(self, mocker: MockerFixture) -> None:
        """to_error_report() for Extract errors includes error_category."""
        worker = _make_mistral_extract_worker(mocker)
        sdk_exc = _make_mistral_error(401, "Invalid API key")
        worker.mistral_client.ocr.process_async.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        mocker.patch(
            "pipelex.plugins.mistral.mistral_extract_worker.MistralFactory.make_mistral_image_url_chunk_from_uri",
            return_value={"type": "image_url", "image_url": "https://example.com/test.png"},
        )

        with pytest.raises(ExtractJobFailureError) as exc_info:
            await worker._extract_page_from_image(image_uri="https://example.com/test.png")  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        report = exc_info.value.to_error_report()
        assert report.error_category == "configuration"
        assert report.retryable is False
