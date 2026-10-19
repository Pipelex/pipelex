"""Tests for pypdfium2 extract worker exception handling and error categorization."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from mthds.protocol.problem.registry import CoreCode

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

    from pipelex.cogt.inference.error_classification import UserActionKind

from pipelex.cogt.exceptions import ExtractJobFailureError, InferenceErrorCategory, find_inference_error_category_in_chain
from pipelex.errors.problem import PipelexProblem, ProblemDiagnostics, ProblemView
from pipelex.providers.pypdfium2.pypdfium2_worker import Pypdfium2Worker
from tests.unit.pipelex.providers.pypdfium2.test_data import Pypdfium2ErrorHandlingTestData


def _make_pypdfium2_worker(mocker: MockerFixture) -> Pypdfium2Worker:
    """Create a minimal Pypdfium2Worker with mocked internals."""
    worker = object.__new__(Pypdfium2Worker)
    mock_model = mocker.MagicMock()
    mock_model.desc = "test-pypdfium2"
    mock_model.model_id = "pypdfium2"
    mock_model.name = "pypdfium2"
    worker.inference_model = mock_model
    return worker


def _make_extract_job(mocker: MockerFixture) -> Any:
    """Create a mock ExtractJob for pypdfium2 worker."""
    job = mocker.MagicMock()
    job.extract_input.image_uri = None
    job.extract_input.document_uri = "/tmp/test.pdf"  # ruff: ignore[hardcoded-temp-file]
    job.job_params.max_nb_images = 0  # No images, simplifies the test
    job.job_report.extract_tokens_usage = None
    return job


def _diagnostics_of(problem: PipelexProblem) -> ProblemDiagnostics:
    """The operator's diagnostics of a problem built in the operator view."""
    assert problem.diagnostics is not None
    return problem.diagnostics


@pytest.mark.asyncio(loop_scope="class")
class TestPypdfium2WorkerErrorHandling:
    """Tests for pypdfium2 extract worker exception handling and error categorization."""

    @pytest.mark.parametrize(
        ("_topic", "exception_class", "exception_message", "expected_category", "expected_user_action_kind"),
        Pypdfium2ErrorHandlingTestData.EXTRACTION_ERROR_CASES,
    )
    async def test_extraction_error_categorization(
        self,
        mocker: MockerFixture,
        _topic: str,
        exception_class: type[Exception],
        exception_message: str,
        expected_category: InferenceErrorCategory,
        expected_user_action_kind: UserActionKind,
    ) -> None:
        """PDF extraction errors are caught and categorized correctly."""
        worker = _make_pypdfium2_worker(mocker)
        sdk_exc = exception_class(exception_message)

        # Mock _resolve_pdf_uri to return a simple path (bypasses URI resolution)
        mocker.patch.object(
            worker,
            "_resolve_pdf_uri",
            new_callable=mocker.AsyncMock,
            return_value="/tmp/test.pdf",  # ruff: ignore[hardcoded-temp-file]
        )

        # Mock pypdfium2_renderer methods to raise the exception
        mocker.patch(
            "pipelex.providers.pypdfium2.pypdfium2_worker.pypdfium2_renderer.extract_text_from_pdf_pages",
            new_callable=mocker.AsyncMock,
            side_effect=sdk_exc,
        )

        with pytest.raises(ExtractJobFailureError) as exc_info:
            await worker._extract_pages(extract_job=_make_extract_job(mocker))  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is expected_category
        assert exc_info.value.__cause__ is sdk_exc
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is expected_user_action_kind

    @pytest.mark.builds_problems_without_required_params(reason="an extract worker reads its source by URI and never learns the input it came from")
    async def test_problem_for_file_not_found(self, mocker: MockerFixture) -> None:
        """A FileNotFoundError is a CONTENT failure, and its problem invites no retry."""
        worker = _make_pypdfium2_worker(mocker)
        sdk_exc = FileNotFoundError("No such file: /tmp/missing.pdf")

        mocker.patch.object(
            worker,
            "_resolve_pdf_uri",
            new_callable=mocker.AsyncMock,
            return_value="/tmp/missing.pdf",  # ruff: ignore[hardcoded-temp-file]
        )
        mocker.patch(
            "pipelex.providers.pypdfium2.pypdfium2_worker.pypdfium2_renderer.extract_text_from_pdf_pages",
            new_callable=mocker.AsyncMock,
            side_effect=sdk_exc,
        )

        with pytest.raises(ExtractJobFailureError) as exc_info:
            await worker._extract_pages(extract_job=_make_extract_job(mocker))  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        error = exc_info.value
        problem = error.to_problem(view=ProblemView.OPERATOR)
        assert find_inference_error_category_in_chain(error) == "content"
        assert problem.is_retryable is False
        assert _diagnostics_of(problem).error_class == "ExtractJobFailureError"

    async def test_problem_for_os_error_is_the_runtime_s(self, mocker: MockerFixture) -> None:
        """A local disk failure is this machine's, not the input's and not one a retry is known to clear: runtime.unexpected."""
        worker = _make_pypdfium2_worker(mocker)
        sdk_exc = OSError("Disk read error")

        mocker.patch.object(
            worker,
            "_resolve_pdf_uri",
            new_callable=mocker.AsyncMock,
            return_value="/tmp/test.pdf",  # ruff: ignore[hardcoded-temp-file]
        )
        mocker.patch(
            "pipelex.providers.pypdfium2.pypdfium2_worker.pypdfium2_renderer.extract_text_from_pdf_pages",
            new_callable=mocker.AsyncMock,
            side_effect=sdk_exc,
        )

        with pytest.raises(ExtractJobFailureError) as exc_info:
            await worker._extract_pages(extract_job=_make_extract_job(mocker))  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        error = exc_info.value
        problem = error.to_problem(view=ProblemView.OPERATOR)
        assert find_inference_error_category_in_chain(error) == "unknown"
        assert problem.code == CoreCode.RUNTIME_UNEXPECTED
        assert problem.is_retryable is False
