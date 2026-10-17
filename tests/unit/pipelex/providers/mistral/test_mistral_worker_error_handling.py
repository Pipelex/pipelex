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
    ExtractModelNotFoundError,
    InferenceErrorCategory,
    LLMCompletionError,
    LLMModelNotFoundError,
    find_inference_error_category_in_chain,
)
from pipelex.cogt.inference.error_classification import UserActionKind
from pipelex.errors.problem import PipelexProblem, ProblemDiagnostics, ProblemView
from pipelex.providers.mistral.mistral_extract_worker import MistralExtractWorker
from pipelex.providers.mistral.mistral_llm_worker import MistralLLMWorker
from tests.unit.pipelex.providers.mistral.test_data import (
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


def _diagnostics_of(problem: PipelexProblem) -> ProblemDiagnostics:
    """The operator's diagnostics of a problem built in the operator view."""
    assert problem.diagnostics is not None
    return problem.diagnostics


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
            await worker._gen_text(llm_job=_make_llm_job(mocker))  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is expected_category
        assert exc_info.value.__cause__ is sdk_exc
        if expected_action_substring:
            assert exc_info.value.user_action is not None
            assert expected_action_substring in exc_info.value.user_action.detail.lower()

    async def test_llm_worker_unhandled_4xx_is_configuration(self, mocker: MockerFixture) -> None:
        """A MistralError with an unhandled 4xx status is non-retryable CONFIGURATION, not TRANSIENT."""
        worker = _make_mistral_llm_worker(mocker)
        sdk_exc = _make_mistral_error(409, "Conflict")
        worker.mistral_client_for_text.chat.complete_async.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(LLMCompletionError) as exc_info:
            await worker._gen_text(llm_job=_make_llm_job(mocker))  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.CONFIGURATION
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.CHANGE_INPUT
        assert exc_info.value.__cause__ is sdk_exc

    @pytest.mark.parametrize(
        ("response_shape", "expected_detail"),
        [
            pytest.param("no_response", "Mistral returned an empty response — wait a moment, then run it again", id="no_response"),
            pytest.param("no_choices", "Mistral returned a response with no choices — wait a moment, then run it again", id="no_choices"),
            pytest.param(
                "choice_without_message",
                "Mistral returned a choice with no message — wait a moment, then run it again",
                id="choice_without_message",
            ),
        ],
    )
    async def test_llm_worker_malformed_response_is_transient(self, mocker: MockerFixture, response_shape: str, expected_detail: str) -> None:
        """A malformed response is a transient failure, not read as empty text, and its advice says to wait then run again."""
        worker = _make_mistral_llm_worker(mocker)
        response: Any
        if response_shape == "no_response":
            response = None
        else:
            response = mocker.MagicMock()
            response.choices = [] if response_shape == "no_choices" else [mocker.MagicMock(message=None)]
        worker.mistral_client_for_text.chat.complete_async.return_value = response  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(LLMCompletionError) as exc_info:
            await worker._gen_text(llm_job=_make_llm_job(mocker))  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.TRANSIENT
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.WAIT_AND_RETRY
        assert exc_info.value.user_action.detail == expected_detail

    async def test_llm_worker_not_found_raises_llm_model_not_found_error(self, mocker: MockerFixture) -> None:
        """A 404 MistralError specializes to LLMModelNotFoundError (CONFIGURATION) on the LLM path."""
        worker = _make_mistral_llm_worker(mocker)
        sdk_exc = _make_mistral_error(404, "Model mistral-unknown not found")
        worker.mistral_client_for_text.chat.complete_async.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(LLMModelNotFoundError) as exc_info:
            await worker._gen_text(llm_job=_make_llm_job(mocker))  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.CONFIGURATION
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.CHANGE_MODEL
        assert exc_info.value.__cause__ is sdk_exc

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
            "pipelex.providers.mistral.mistral_extract_worker.MistralFactory.make_mistral_image_url_chunk_from_uri",
            return_value={"type": "image_url", "image_url": "https://example.com/test.png"},
        )

        with pytest.raises(ExtractJobFailureError) as exc_info:
            await worker._extract_page_from_image(  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]
                image_uri="https://example.com/test.png",
                extract_job_params=mocker.MagicMock(max_nb_images=None, image_min_size=None),
            )

        assert exc_info.value.error_category is expected_category
        assert exc_info.value.__cause__ is sdk_exc
        if expected_action_substring:
            assert exc_info.value.user_action is not None
            assert expected_action_substring in exc_info.value.user_action.detail.lower()

    async def test_extract_worker_not_found_raises_extract_model_not_found_error(self, mocker: MockerFixture) -> None:
        """A 404 MistralError specializes to ExtractModelNotFoundError (CONFIGURATION) on the Extract path."""
        worker = _make_mistral_extract_worker(mocker)
        sdk_exc = _make_mistral_error(404, "Model mistral-ocr-unknown not found")
        worker.mistral_client.ocr.process_async.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        mocker.patch(
            "pipelex.providers.mistral.mistral_extract_worker.MistralFactory.make_mistral_image_url_chunk_from_uri",
            return_value={"type": "image_url", "image_url": "https://example.com/test.png"},
        )

        with pytest.raises(ExtractModelNotFoundError) as exc_info:
            await worker._extract_page_from_image(  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]
                image_uri="https://example.com/test.png",
                extract_job_params=mocker.MagicMock(max_nb_images=None, image_min_size=None),
            )

        assert exc_info.value.error_category is InferenceErrorCategory.CONFIGURATION
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.CHANGE_MODEL
        assert exc_info.value.__cause__ is sdk_exc

    # ---- Problem integration ----

    async def test_llm_problem_transient_is_retryable(self, mocker: MockerFixture) -> None:
        """The problem of a TRANSIENT LLM error invites a retry."""
        worker = _make_mistral_llm_worker(mocker)
        sdk_exc = _make_mistral_error(429, "Rate limit exceeded")
        worker.mistral_client_for_text.chat.complete_async.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(LLMCompletionError) as exc_info:
            await worker._gen_text(llm_job=_make_llm_job(mocker))  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        error = exc_info.value
        problem = error.to_problem(view=ProblemView.OPERATOR)
        assert find_inference_error_category_in_chain(error) == "transient"
        assert problem.is_retryable is True
        assert _diagnostics_of(problem).error_class == "LLMCompletionError"

    async def test_llm_problem_capacity_not_retryable(self, mocker: MockerFixture) -> None:
        """The problem of a CAPACITY LLM error invites no retry."""
        worker = _make_mistral_llm_worker(mocker)
        sdk_exc = _make_mistral_error(402, "Payment required: insufficient credits")
        worker.mistral_client_for_text.chat.complete_async.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        with pytest.raises(LLMCompletionError) as exc_info:
            await worker._gen_text(llm_job=_make_llm_job(mocker))  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        error = exc_info.value
        problem = error.to_problem(view=ProblemView.OPERATOR)
        assert find_inference_error_category_in_chain(error) == "capacity"
        assert problem.is_retryable is False

    async def test_extract_problem_includes_category(self, mocker: MockerFixture) -> None:
        """An extract error keeps its category on the chain."""
        worker = _make_mistral_extract_worker(mocker)
        sdk_exc = _make_mistral_error(401, "Invalid API key")
        worker.mistral_client.ocr.process_async.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        mocker.patch(
            "pipelex.providers.mistral.mistral_extract_worker.MistralFactory.make_mistral_image_url_chunk_from_uri",
            return_value={"type": "image_url", "image_url": "https://example.com/test.png"},
        )

        with pytest.raises(ExtractJobFailureError) as exc_info:
            await worker._extract_page_from_image(  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]
                image_uri="https://example.com/test.png",
                extract_job_params=mocker.MagicMock(max_nb_images=None, image_min_size=None),
            )

        error = exc_info.value
        problem = error.to_problem(view=ProblemView.OPERATOR)
        assert find_inference_error_category_in_chain(error) == "configuration"
        assert problem.is_retryable is False
