"""Tests for OpenAI worker SDK exception handling and error categorization."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx
import openai
import pytest

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

from pipelex.cogt.exceptions import (
    ImgGenGenerationError,
    InferenceErrorCategory,
    LLMCompletionError,
)
from pipelex.plugins.openai.openai_completions_llm_worker import OpenAICompletionsLLMWorker
from pipelex.plugins.openai.openai_img_gen_worker import OpenAIImgGenWorker
from pipelex.plugins.openai.openai_responses_llm_worker import OpenAIResponsesLLMWorker
from tests.unit.pipelex.plugins.openai.test_data import OpenAIErrorHandlingTestData


def _mock_httpx_response(status_code: int = 429) -> httpx.Response:
    """Create a minimal httpx.Response for constructing SDK exceptions."""
    request = httpx.Request("POST", "https://api.openai.com/v1/test")
    return httpx.Response(status_code=status_code, request=request)


def _make_openai_rate_limit_error(message: str) -> openai.RateLimitError:
    return openai.RateLimitError(message, response=_mock_httpx_response(429), body=None)


def _make_openai_bad_request_error(message: str) -> openai.BadRequestError:
    return openai.BadRequestError(message, response=_mock_httpx_response(400), body=None)


def _make_openai_timeout_error() -> openai.APITimeoutError:
    request = httpx.Request("POST", "https://api.openai.com/v1/test")
    return openai.APITimeoutError(request=request)


def _make_openai_connection_error(message: str = "Connection error.") -> openai.APIConnectionError:
    request = httpx.Request("POST", "https://api.openai.com/v1/test")
    return openai.APIConnectionError(message=message, request=request)


def _make_openai_not_found_error(message: str) -> openai.NotFoundError:
    return openai.NotFoundError(message, response=_mock_httpx_response(404), body=None)


def _make_openai_auth_error(message: str) -> openai.AuthenticationError:
    return openai.AuthenticationError(message, response=_mock_httpx_response(401), body=None)


def _make_completions_llm_worker(mocker: MockerFixture) -> OpenAICompletionsLLMWorker:
    """Create a minimal OpenAICompletionsLLMWorker with mocked internals."""
    worker = object.__new__(OpenAICompletionsLLMWorker)
    mock_model = mocker.MagicMock()
    mock_model.desc = "test-model-desc"
    mock_model.model_id = "gpt-4o"
    mock_model.name = "gpt-4o"
    mock_model.thinking_mode = None
    worker.inference_model = mock_model

    mock_client = mocker.MagicMock()
    mock_client.chat.completions.create = mocker.AsyncMock()
    worker.openai_client_for_text = mock_client

    mock_factory = mocker.MagicMock()
    mock_factory.make_simple_messages = mocker.AsyncMock(return_value=[])
    mock_factory.make_extras = mocker.MagicMock(return_value=({}, {}))
    worker.openai_completions_factory = mock_factory

    return worker


def _make_responses_llm_worker(mocker: MockerFixture) -> OpenAIResponsesLLMWorker:
    """Create a minimal OpenAIResponsesLLMWorker with mocked internals."""
    worker = object.__new__(OpenAIResponsesLLMWorker)
    mock_model = mocker.MagicMock()
    mock_model.desc = "test-model-desc"
    mock_model.model_id = "gpt-4o"
    mock_model.name = "gpt-4o"
    mock_model.thinking_mode = None
    worker.inference_model = mock_model

    mock_client = mocker.MagicMock()
    mock_client.responses.create = mocker.AsyncMock()
    worker.openai_client_for_responses = mock_client

    mock_factory = mocker.MagicMock()
    mock_factory.make_input_items = mocker.AsyncMock(return_value=[])
    mock_factory.make_extras = mocker.MagicMock(return_value=({}, {}))
    worker.openai_responses_factory = mock_factory

    return worker


def _make_img_gen_worker(mocker: MockerFixture) -> OpenAIImgGenWorker:
    """Create a minimal OpenAIImgGenWorker with mocked internals."""
    worker = object.__new__(OpenAIImgGenWorker)
    mock_model = mocker.MagicMock()
    mock_model.desc = "test-model-desc"
    mock_model.model_id = "gpt-image-1"
    mock_model.name = "gpt-image-1"
    mock_model.rules = mocker.MagicMock()
    worker.inference_model = mock_model

    mock_client = mocker.MagicMock()
    mock_client.images.generate = mocker.AsyncMock()
    mock_client.images.edit = mocker.AsyncMock()
    worker.openai_client = mock_client

    mocker.patch(
        "pipelex.plugins.openai.openai_img_gen_worker.ImgGenArgsFactory.make_args_for_model",
        new_callable=mocker.AsyncMock,
        return_value={"prompt": "a cute cat", "model": "gpt-image-1"},
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
class TestOpenAIWorkerErrorHandling:
    """Tests for OpenAI worker SDK exception handling and error categorization."""

    # ---- RateLimitError tests (completions LLM worker) ----

    @pytest.mark.parametrize(
        ("_topic", "error_message", "expected_category", "expected_action_substring"),
        OpenAIErrorHandlingTestData.RATE_LIMIT_CASES,
    )
    async def test_completions_llm_rate_limit(
        self,
        mocker: MockerFixture,
        _topic: str,
        error_message: str,
        expected_category: InferenceErrorCategory,
        expected_action_substring: str | None,
    ) -> None:
        """RateLimitError is caught and categorized correctly (TRANSIENT or CAPACITY)."""
        worker = _make_completions_llm_worker(mocker)
        sdk_exc = _make_openai_rate_limit_error(error_message)
        worker.openai_client_for_text.chat.completions.create.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(LLMCompletionError) as exc_info:
            await worker._gen_text(llm_job=_make_llm_job(mocker))  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is expected_category
        assert exc_info.value.__cause__ is sdk_exc
        if expected_action_substring:
            assert exc_info.value.user_action is not None
            assert expected_action_substring in exc_info.value.user_action.lower()

    # ---- APITimeoutError tests ----

    @pytest.mark.parametrize(
        ("_topic", "_error_message", "expected_category"),
        OpenAIErrorHandlingTestData.TIMEOUT_CASES,
    )
    async def test_completions_llm_timeout(
        self,
        mocker: MockerFixture,
        _topic: str,
        _error_message: str,
        expected_category: InferenceErrorCategory,
    ) -> None:
        """APITimeoutError is caught and categorized as TRANSIENT."""
        worker = _make_completions_llm_worker(mocker)
        sdk_exc = _make_openai_timeout_error()
        worker.openai_client_for_text.chat.completions.create.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(LLMCompletionError) as exc_info:
            await worker._gen_text(llm_job=_make_llm_job(mocker))  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is expected_category
        assert exc_info.value.__cause__ is sdk_exc

    # ---- BadRequestError tests with content policy detection ----

    @pytest.mark.parametrize(
        ("_topic", "error_message", "expected_category", "expected_action_substring"),
        OpenAIErrorHandlingTestData.BAD_REQUEST_CASES,
    )
    async def test_completions_llm_bad_request(
        self,
        mocker: MockerFixture,
        _topic: str,
        error_message: str,
        expected_category: InferenceErrorCategory,
        expected_action_substring: str | None,
    ) -> None:
        """BadRequestError is caught with content policy detection."""
        worker = _make_completions_llm_worker(mocker)
        sdk_exc = _make_openai_bad_request_error(error_message)
        worker.openai_client_for_text.chat.completions.create.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(LLMCompletionError) as exc_info:
            await worker._gen_text(llm_job=_make_llm_job(mocker))  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is expected_category
        assert exc_info.value.__cause__ is sdk_exc
        if expected_action_substring:
            assert exc_info.value.user_action is not None
            assert expected_action_substring in exc_info.value.user_action.lower()

    # ---- Existing exception categories ----

    async def test_completions_llm_not_found_has_configuration_category(self, mocker: MockerFixture) -> None:
        """NotFoundError should be categorized as CONFIGURATION."""
        worker = _make_completions_llm_worker(mocker)
        sdk_exc = _make_openai_not_found_error("model gpt-99 not found")
        worker.openai_client_for_text.chat.completions.create.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(LLMCompletionError) as exc_info:
            await worker._gen_text(llm_job=_make_llm_job(mocker))  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.CONFIGURATION
        assert exc_info.value.__cause__ is sdk_exc

    async def test_completions_llm_connection_error_has_transient_category(self, mocker: MockerFixture) -> None:
        """APIConnectionError should be categorized as TRANSIENT."""
        worker = _make_completions_llm_worker(mocker)
        sdk_exc = _make_openai_connection_error("Connection refused")
        worker.openai_client_for_text.chat.completions.create.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(LLMCompletionError) as exc_info:
            await worker._gen_text(llm_job=_make_llm_job(mocker))  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.TRANSIENT
        assert exc_info.value.__cause__ is sdk_exc

    async def test_completions_llm_auth_error_has_configuration_category(self, mocker: MockerFixture) -> None:
        """AuthenticationError should be categorized as CONFIGURATION."""
        worker = _make_completions_llm_worker(mocker)
        sdk_exc = _make_openai_auth_error("Invalid API key")
        worker.openai_client_for_text.chat.completions.create.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(LLMCompletionError) as exc_info:
            await worker._gen_text(llm_job=_make_llm_job(mocker))  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.CONFIGURATION
        assert exc_info.value.__cause__ is sdk_exc

    # ---- Responses LLM worker ----

    async def test_responses_llm_rate_limit_transient(self, mocker: MockerFixture) -> None:
        """Responses worker: generic rate limit is TRANSIENT."""
        worker = _make_responses_llm_worker(mocker)
        sdk_exc = _make_openai_rate_limit_error("Rate limit exceeded")
        worker.openai_client_for_responses.responses.create.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(LLMCompletionError) as exc_info:
            await worker._gen_text(llm_job=_make_llm_job(mocker))  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.TRANSIENT
        assert exc_info.value.__cause__ is sdk_exc

    async def test_responses_llm_rate_limit_quota(self, mocker: MockerFixture) -> None:
        """Responses worker: quota exhaustion rate limit is CAPACITY."""
        worker = _make_responses_llm_worker(mocker)
        sdk_exc = _make_openai_rate_limit_error("insufficient_quota")
        worker.openai_client_for_responses.responses.create.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(LLMCompletionError) as exc_info:
            await worker._gen_text(llm_job=_make_llm_job(mocker))  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.CAPACITY

    # ---- ImgGen worker ----

    async def test_img_gen_rate_limit_transient(self, mocker: MockerFixture) -> None:
        """ImgGen worker: generic rate limit raises ImgGenGenerationError with TRANSIENT."""
        worker = _make_img_gen_worker(mocker)
        sdk_exc = _make_openai_rate_limit_error("Rate limit exceeded")
        worker.openai_client.images.generate.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(ImgGenGenerationError) as exc_info:
            await worker._gen_image_list(img_gen_job=_make_img_gen_job(mocker), nb_images=1)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.TRANSIENT
        assert exc_info.value.__cause__ is sdk_exc

    async def test_img_gen_auth_error(self, mocker: MockerFixture) -> None:
        """ImgGen worker: AuthenticationError raises ImgGenGenerationError with CONFIGURATION."""
        worker = _make_img_gen_worker(mocker)
        sdk_exc = _make_openai_auth_error("Invalid API key")
        worker.openai_client.images.generate.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(ImgGenGenerationError) as exc_info:
            await worker._gen_image_list(img_gen_job=_make_img_gen_job(mocker), nb_images=1)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.CONFIGURATION
        assert exc_info.value.__cause__ is sdk_exc

    # ---- to_error_report() integration ----

    async def test_error_report_includes_category_and_retryable(self, mocker: MockerFixture) -> None:
        """to_error_report() includes error_category and retryable from the exception."""
        worker = _make_completions_llm_worker(mocker)
        sdk_exc = _make_openai_rate_limit_error("Rate limit exceeded")
        worker.openai_client_for_text.chat.completions.create.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(LLMCompletionError) as exc_info:
            await worker._gen_text(llm_job=_make_llm_job(mocker))  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        report = exc_info.value.to_error_report()
        assert report.error_category == "transient"
        assert report.retryable is True
        assert report.error_type == "LLMCompletionError"

    async def test_error_report_capacity_not_retryable(self, mocker: MockerFixture) -> None:
        """to_error_report() for CAPACITY errors has retryable=False."""
        worker = _make_completions_llm_worker(mocker)
        sdk_exc = _make_openai_rate_limit_error("insufficient_quota")
        worker.openai_client_for_text.chat.completions.create.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(LLMCompletionError) as exc_info:
            await worker._gen_text(llm_job=_make_llm_job(mocker))  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        report = exc_info.value.to_error_report()
        assert report.error_category == "capacity"
        assert report.retryable is False
