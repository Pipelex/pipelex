"""Tests for HuggingFace ImgGen worker SDK exception handling and error categorization."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx
import pytest
from huggingface_hub.errors import HfHubHTTPError, InferenceTimeoutError

from pipelex.cogt.exceptions import ImgGenGenerationError, InferenceErrorCategory, find_inference_error_category_in_chain
from pipelex.cogt.inference.error_classification import UserActionKind
from pipelex.errors.problem import PipelexProblem, ProblemDiagnostics, ProblemView
from pipelex.providers.huggingface.huggingface_img_gen_worker import HuggingFaceImgGenWorker
from tests.unit.pipelex.providers.huggingface.test_data import HuggingFaceErrorHandlingTestData

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


def _make_hf_http_error(status_code: int | None, message: str) -> HfHubHTTPError:
    """Create a minimal HfHubHTTPError for testing with optional status code."""
    response = httpx.Response(
        status_code=status_code or 500,
        request=httpx.Request("POST", "https://router.huggingface.co/test"),
    )
    exc = HfHubHTTPError(message, response=response)
    if status_code is None:
        # Simulate a network-level failure carrying no response metadata
        exc.response = None  # type: ignore[assignment]  # pyright: ignore[reportAttributeAccessIssue]
    return exc


def _make_inference_timeout_error(message: str = "Inference timed out") -> InferenceTimeoutError:
    """Create a minimal InferenceTimeoutError for testing."""
    return InferenceTimeoutError(message)


def _make_hf_img_gen_worker(mocker: MockerFixture) -> HuggingFaceImgGenWorker:
    """Create a minimal HuggingFaceImgGenWorker with mocked internals."""
    worker = object.__new__(HuggingFaceImgGenWorker)
    mock_model = mocker.MagicMock()
    mock_model.desc = "test-hf-model"
    mock_model.model_id = "stabilityai/stable-diffusion-xl-base-1.0"
    mock_model.name = "sdxl-base"
    mock_model.rules = mocker.MagicMock()
    worker.inference_model = mock_model

    mock_client = mocker.MagicMock()
    mock_client.text_to_image = mocker.AsyncMock()
    worker.hf_async_client = mock_client

    return worker


def _make_img_gen_job(mocker: MockerFixture) -> Any:
    """Create a mock ImgGen job."""
    job = mocker.MagicMock()
    job.img_gen_prompt.positive_text = "a sunset over mountains"
    job.job_params.output_format = None
    job.job_report.img_gen_tokens_usage = None
    return job


def _diagnostics_of(problem: PipelexProblem) -> ProblemDiagnostics:
    """The operator's diagnostics of a problem built in the operator view."""
    assert problem.diagnostics is not None
    return problem.diagnostics


@pytest.mark.asyncio(loop_scope="class")
class TestHuggingFaceWorkerErrorHandling:
    """Tests for HuggingFace ImgGen worker SDK exception handling and error categorization."""

    @pytest.mark.parametrize(
        ("_topic", "status_code", "message", "expected_category", "expected_user_action_kind"),
        HuggingFaceErrorHandlingTestData.HF_HTTP_ERROR_CASES,
    )
    async def test_hf_http_error_categorization(
        self,
        mocker: MockerFixture,
        _topic: str,
        status_code: int | None,
        message: str,
        expected_category: InferenceErrorCategory,
        expected_user_action_kind: UserActionKind,
    ) -> None:
        """HfHubHTTPError is caught and categorized correctly based on status code."""
        worker = _make_hf_img_gen_worker(mocker)
        sdk_exc = _make_hf_http_error(status_code, message)
        worker.hf_async_client.text_to_image.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        mocker.patch(
            "pipelex.providers.huggingface.huggingface_img_gen_worker.ImgGenArgsFactory.make_args_for_model",
            new_callable=mocker.AsyncMock,
            return_value={"prompt": "test", "model": "test-model-id"},
        )

        with pytest.raises(ImgGenGenerationError) as exc_info:
            await worker._generate_single_image(img_gen_job=_make_img_gen_job(mocker))  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is expected_category
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is expected_user_action_kind
        assert exc_info.value.__cause__ is sdk_exc

    @pytest.mark.parametrize(
        ("_topic", "expected_category", "expected_user_action_kind"),
        HuggingFaceErrorHandlingTestData.TIMEOUT_CASES,
    )
    async def test_inference_timeout_is_an_unknown_outcome(
        self,
        mocker: MockerFixture,
        _topic: str,
        expected_category: InferenceErrorCategory,
        expected_user_action_kind: UserActionKind,
    ) -> None:
        """InferenceTimeoutError is caught and categorized as TRANSIENT."""
        worker = _make_hf_img_gen_worker(mocker)
        sdk_exc = _make_inference_timeout_error()
        worker.hf_async_client.text_to_image.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        mocker.patch(
            "pipelex.providers.huggingface.huggingface_img_gen_worker.ImgGenArgsFactory.make_args_for_model",
            new_callable=mocker.AsyncMock,
            return_value={"prompt": "test", "model": "test-model-id"},
        )

        with pytest.raises(ImgGenGenerationError) as exc_info:
            await worker._generate_single_image(img_gen_job=_make_img_gen_job(mocker))  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is expected_category
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is expected_user_action_kind
        assert exc_info.value.__cause__ is sdk_exc

    async def test_problem_includes_category(self, mocker: MockerFixture) -> None:
        """The category stays on the chain, and the problem takes the retry verdict of the code it gives."""
        worker = _make_hf_img_gen_worker(mocker)
        sdk_exc = _make_hf_http_error(401, "Invalid token")
        worker.hf_async_client.text_to_image.side_effect = sdk_exc  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

        mocker.patch(
            "pipelex.providers.huggingface.huggingface_img_gen_worker.ImgGenArgsFactory.make_args_for_model",
            new_callable=mocker.AsyncMock,
            return_value={"prompt": "test", "model": "test-model-id"},
        )

        with pytest.raises(ImgGenGenerationError) as exc_info:
            await worker._generate_single_image(img_gen_job=_make_img_gen_job(mocker))  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        error = exc_info.value
        problem = error.to_problem(view=ProblemView.OPERATOR)
        assert find_inference_error_category_in_chain(error) == "configuration"
        assert problem.is_retryable is False
        assert _diagnostics_of(problem).error_class == "ImgGenGenerationError"
        assert exc_info.value.error_category is InferenceErrorCategory.CONFIGURATION
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.CHECK_CREDENTIALS
