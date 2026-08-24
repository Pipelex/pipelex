"""Tests for Docling extract worker exception handling and error categorization."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

    from pipelex.cogt.inference.error_classification import UserActionKind

from pipelex.cogt.exceptions import ExtractJobFailureError, InferenceErrorCategory
from pipelex.providers.docling.docling_extract_worker import DoclingExtractWorker
from pipelex.tools.uri.prepared_file import PreparedFileLocalPath
from tests.unit.pipelex.providers.docling.test_data import DoclingErrorHandlingTestData


def _make_docling_extract_worker(mocker: MockerFixture) -> DoclingExtractWorker:
    """Create a minimal DoclingExtractWorker with mocked internals."""
    worker = object.__new__(DoclingExtractWorker)
    mock_model = mocker.MagicMock()
    mock_model.desc = "test-docling-model"
    mock_model.model_id = "docling"
    mock_model.name = "docling"
    worker.inference_model = mock_model

    mock_sdk = mocker.MagicMock()
    mock_sdk.document_converter = mocker.MagicMock()
    worker.docling_sdk = mock_sdk

    return worker


@pytest.mark.asyncio(loop_scope="class")
class TestDoclingWorkerErrorHandling:
    """Tests for Docling extract worker exception handling and error categorization."""

    @pytest.mark.parametrize(
        ("_topic", "exception_class", "exception_message", "expected_category", "expected_user_action_kind"),
        DoclingErrorHandlingTestData.EXTRACTION_ERROR_CASES,
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
        """Docling conversion errors are caught and categorized correctly."""
        worker = _make_docling_extract_worker(mocker)
        sdk_exc = exception_class(exception_message)

        # Mock asyncio.to_thread to raise the exception (simulating docling conversion failure)
        mocker.patch(
            "pipelex.providers.docling.docling_extract_worker.asyncio.to_thread",
            side_effect=sdk_exc,
        )
        # Mock prepare_file_from_uri to return a local path that the match statement can handle
        mock_prepared_file = PreparedFileLocalPath(path="/tmp/test.pdf")  # ruff: ignore[hardcoded-temp-file]
        mocker.patch(
            "pipelex.providers.docling.docling_extract_worker.prepare_file_from_uri",
            new_callable=mocker.AsyncMock,
            return_value=mock_prepared_file,
        )

        with pytest.raises(ExtractJobFailureError) as exc_info:
            await worker._extract_from_source(source_uri="/tmp/test.pdf")  # ruff: ignore[private-member-access, hardcoded-temp-file]  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is expected_category
        assert exc_info.value.__cause__ is sdk_exc
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is expected_user_action_kind

    async def test_error_report_for_file_not_found(self, mocker: MockerFixture) -> None:
        """to_error_report() for FileNotFoundError has CONTENT category."""
        worker = _make_docling_extract_worker(mocker)
        sdk_exc = FileNotFoundError("No such file: /tmp/missing.pdf")

        mocker.patch(
            "pipelex.providers.docling.docling_extract_worker.asyncio.to_thread",
            side_effect=sdk_exc,
        )
        mock_prepared_file = PreparedFileLocalPath(path="/tmp/test.pdf")  # ruff: ignore[hardcoded-temp-file]
        mocker.patch(
            "pipelex.providers.docling.docling_extract_worker.prepare_file_from_uri",
            new_callable=mocker.AsyncMock,
            return_value=mock_prepared_file,
        )

        with pytest.raises(ExtractJobFailureError) as exc_info:
            await worker._extract_from_source(source_uri="/tmp/test.pdf")  # ruff: ignore[private-member-access, hardcoded-temp-file]  # pyright: ignore[reportPrivateUsage]

        report = exc_info.value.to_error_report()
        assert report.error_category == "content"
        assert report.retryable is False
        assert report.error_type == "ExtractJobFailureError"

    async def test_error_report_for_io_error(self, mocker: MockerFixture) -> None:
        """to_error_report() for OSError has TRANSIENT category and is retryable."""
        worker = _make_docling_extract_worker(mocker)
        sdk_exc = OSError("Disk I/O failure")

        mocker.patch(
            "pipelex.providers.docling.docling_extract_worker.asyncio.to_thread",
            side_effect=sdk_exc,
        )
        mock_prepared_file = PreparedFileLocalPath(path="/tmp/test.pdf")  # ruff: ignore[hardcoded-temp-file]
        mocker.patch(
            "pipelex.providers.docling.docling_extract_worker.prepare_file_from_uri",
            new_callable=mocker.AsyncMock,
            return_value=mock_prepared_file,
        )

        with pytest.raises(ExtractJobFailureError) as exc_info:
            await worker._extract_from_source(source_uri="/tmp/test.pdf")  # ruff: ignore[private-member-access, hardcoded-temp-file]  # pyright: ignore[reportPrivateUsage]

        report = exc_info.value.to_error_report()
        assert report.error_category == "transient"
        assert report.retryable is True
