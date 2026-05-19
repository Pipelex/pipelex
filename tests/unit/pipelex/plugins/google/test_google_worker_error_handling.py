"""Tests for Google worker SDK exception handling and error categorization."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from google.genai import errors as genai_errors

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

from pipelex.cogt.exceptions import (
    ImgGenGenerationError,
    ImgGenModelNotFoundError,
    InferenceErrorCategory,
    LLMCompletionError,
    LLMModelNotFoundError,
)
from pipelex.cogt.inference.error_classification import UserActionKind
from pipelex.plugins.google.google_img_gen_worker import GoogleImgGenWorker
from pipelex.plugins.google.google_llm_worker import GoogleLLMWorker
from tests.unit.pipelex.plugins.google.test_data import GoogleErrorHandlingTestData


def _make_google_client_error(code: int, message: str) -> genai_errors.ClientError:
    """Create a ClientError with a minimal response_json dict."""
    response_json = {"message": message, "status": "ERROR"}
    return genai_errors.ClientError(code, response_json, None)


def _make_google_server_error(code: int, message: str) -> genai_errors.ServerError:
    """Create a ServerError with a minimal response_json dict."""
    response_json = {"message": message, "status": "ERROR"}
    return genai_errors.ServerError(code, response_json, None)


def _make_google_llm_worker(mocker: MockerFixture) -> GoogleLLMWorker:
    """Create a minimal GoogleLLMWorker with mocked internals."""
    worker = object.__new__(GoogleLLMWorker)
    mock_model = mocker.MagicMock()
    mock_model.desc = "test-model-desc"
    mock_model.model_id = "gemini-pro"
    mock_model.name = "gemini-pro"
    mock_model.thinking_mode = None
    worker.inference_model = mock_model

    mock_async_client = mocker.MagicMock()
    mock_async_client.models.generate_content = mocker.AsyncMock()
    worker.genai_async_client = mock_async_client

    # Mock the factory so it doesn't try to parse mock prompt objects as real Pydantic types
    mocker.patch(
        "pipelex.plugins.google.google_llm_worker.GoogleFactory.prepare_user_contents",
        new_callable=mocker.AsyncMock,
        return_value=[],
    )

    return worker


def _make_google_img_gen_worker(mocker: MockerFixture) -> GoogleImgGenWorker:
    """Create a minimal GoogleImgGenWorker with mocked internals."""
    worker = object.__new__(GoogleImgGenWorker)
    mock_model = mocker.MagicMock()
    mock_model.desc = "test-model-desc"
    mock_model.model_id = "imagen-3.0-generate-002"
    mock_model.name = "imagen-3.0-generate-002"
    worker.inference_model = mock_model

    mock_async_client = mocker.MagicMock()
    mock_async_client.models.generate_content = mocker.AsyncMock()
    worker.genai_async_client = mock_async_client

    # Mock the factory static methods so they don't fail before the API call
    mocker.patch(
        "pipelex.plugins.google.google_img_gen_worker.GoogleImgGenFactory.aspect_ratio_literal",
        return_value="1:1",
    )
    mocker.patch(
        "pipelex.plugins.google.google_img_gen_worker.GoogleImgGenFactory.dimensions_for_aspect_ratio_and_size",
        return_value=(1024, 1024),
    )

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


def _make_img_gen_job(mocker: MockerFixture) -> Any:
    """Create a mock ImgGen job."""
    job = mocker.MagicMock()
    job.job_params.aspect_ratio = None
    job.job_params.output_format = None
    job.job_params.is_moderated = True
    job.job_params.background = None
    job.job_params.quality = None
    job.img_gen_prompt.positive_text = "a cute cat"
    job.job_report.img_gen_tokens_usage = None
    return job


@pytest.mark.asyncio(loop_scope="class")
class TestGoogleWorkerErrorHandling:
    """Tests for Google worker SDK exception handling and error categorization."""

    # ---- LLM worker ClientError tests (parametrized) ----

    @pytest.mark.parametrize(
        ("_topic", "status_code", "error_message", "expected_category", "expected_action_substring"),
        GoogleErrorHandlingTestData.CLIENT_ERROR_CASES,
    )
    async def test_llm_client_error(
        self,
        mocker: MockerFixture,
        _topic: str,
        status_code: int,
        error_message: str,
        expected_category: InferenceErrorCategory,
        expected_action_substring: str | None,
    ) -> None:
        """ClientError is caught and categorized correctly by the LLM worker."""
        worker = _make_google_llm_worker(mocker)
        sdk_exc = _make_google_client_error(code=status_code, message=error_message)
        worker.genai_async_client.models.generate_content.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(LLMCompletionError) as exc_info:
            await worker._gen_text(llm_job=_make_llm_job(mocker))  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is expected_category
        assert exc_info.value.__cause__ is sdk_exc
        if expected_action_substring:
            assert exc_info.value.user_action is not None
            assert expected_action_substring in exc_info.value.user_action.detail.lower()

    # ---- LLM worker ServerError test ----

    async def test_llm_server_error_has_transient_category(self, mocker: MockerFixture) -> None:
        """ServerError should be categorized as TRANSIENT."""
        worker = _make_google_llm_worker(mocker)
        sdk_exc = _make_google_server_error(code=500, message="Internal server error")
        worker.genai_async_client.models.generate_content.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(LLMCompletionError) as exc_info:
            await worker._gen_text(llm_job=_make_llm_job(mocker))  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.TRANSIENT
        assert exc_info.value.__cause__ is sdk_exc

    # ---- LLM worker not-found test (404 specializes to LLMModelNotFoundError) ----

    async def test_llm_not_found_raises_llm_model_not_found_error(self, mocker: MockerFixture) -> None:
        """A 404 ClientError specializes to LLMModelNotFoundError (CONFIGURATION) on the LLM path."""
        worker = _make_google_llm_worker(mocker)
        sdk_exc = _make_google_client_error(code=404, message="Model gemini-99 not found")
        worker.genai_async_client.models.generate_content.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(LLMModelNotFoundError) as exc_info:
            await worker._gen_text(llm_job=_make_llm_job(mocker))  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.CONFIGURATION
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.CHANGE_MODEL
        assert exc_info.value.__cause__ is sdk_exc

    # ---- ImgGen worker ClientError tests (parametrized) ----

    @pytest.mark.parametrize(
        ("_topic", "status_code", "error_message", "expected_category", "expected_action_substring"),
        GoogleErrorHandlingTestData.CLIENT_ERROR_CASES,
    )
    async def test_img_gen_client_error(
        self,
        mocker: MockerFixture,
        _topic: str,
        status_code: int,
        error_message: str,
        expected_category: InferenceErrorCategory,
        expected_action_substring: str | None,
    ) -> None:
        """ClientError is caught and categorized correctly by the ImgGen worker."""
        worker = _make_google_img_gen_worker(mocker)
        sdk_exc = _make_google_client_error(code=status_code, message=error_message)
        worker.genai_async_client.models.generate_content.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(ImgGenGenerationError) as exc_info:
            await worker._gen_image(img_gen_job=_make_img_gen_job(mocker))  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is expected_category
        assert exc_info.value.__cause__ is sdk_exc
        if expected_action_substring:
            assert exc_info.value.user_action is not None
            assert expected_action_substring in exc_info.value.user_action.detail.lower()

    # ---- ImgGen worker not-found test (404 specializes to ImgGenModelNotFoundError) ----

    async def test_img_gen_not_found_raises_img_gen_model_not_found_error(self, mocker: MockerFixture) -> None:
        """A 404 ClientError specializes to ImgGenModelNotFoundError (CONFIGURATION) on the ImgGen path."""
        worker = _make_google_img_gen_worker(mocker)
        sdk_exc = _make_google_client_error(code=404, message="Model gemini-99 not found")
        worker.genai_async_client.models.generate_content.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(ImgGenModelNotFoundError) as exc_info:
            await worker._gen_image(img_gen_job=_make_img_gen_job(mocker))  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.CONFIGURATION
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.CHANGE_MODEL
        assert exc_info.value.model_handle == "imagen-3.0-generate-002"
        assert exc_info.value.__cause__ is sdk_exc

    # ---- ImgGen worker ServerError test ----

    async def test_img_gen_server_error_has_transient_category(self, mocker: MockerFixture) -> None:
        """ServerError should be categorized as TRANSIENT for ImgGen worker."""
        worker = _make_google_img_gen_worker(mocker)
        sdk_exc = _make_google_server_error(code=500, message="Internal server error")
        worker.genai_async_client.models.generate_content.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(ImgGenGenerationError) as exc_info:
            await worker._gen_image(img_gen_job=_make_img_gen_job(mocker))  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.TRANSIENT
        assert exc_info.value.__cause__ is sdk_exc

    # ---- to_error_report() integration ----

    async def test_error_report_includes_category_and_retryable(self, mocker: MockerFixture) -> None:
        """to_error_report() includes error_category and retryable from the exception."""
        worker = _make_google_llm_worker(mocker)
        sdk_exc = _make_google_client_error(code=429, message="Too many requests")
        worker.genai_async_client.models.generate_content.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(LLMCompletionError) as exc_info:
            await worker._gen_text(llm_job=_make_llm_job(mocker))  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        report = exc_info.value.to_error_report()
        assert report.error_category == "transient"
        assert report.retryable is True
        assert report.error_type == "LLMCompletionError"

    async def test_error_report_capacity_not_retryable(self, mocker: MockerFixture) -> None:
        """to_error_report() for CAPACITY errors has retryable=False."""
        worker = _make_google_llm_worker(mocker)
        sdk_exc = _make_google_client_error(code=429, message="Resource has been exhausted (e.g. check quota)")
        worker.genai_async_client.models.generate_content.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(LLMCompletionError) as exc_info:
            await worker._gen_text(llm_job=_make_llm_job(mocker))  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        report = exc_info.value.to_error_report()
        assert report.error_category == "capacity"
        assert report.retryable is False
