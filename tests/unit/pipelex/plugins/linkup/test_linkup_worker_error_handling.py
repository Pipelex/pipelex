"""Tests for Linkup extract and search worker exception handling and error categorization."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from linkup import LinkupAuthenticationError, LinkupInsufficientCreditError, LinkupTooManyRequestsError

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

from pipelex.cogt.exceptions import ExtractJobFailureError, InferenceErrorCategory, SearchJobFailureError
from pipelex.cogt.inference.error_classification import UserActionKind
from pipelex.plugins.linkup.linkup_extract_worker import LinkupExtractWorker
from pipelex.plugins.linkup.linkup_search_worker import LinkupSearchWorker
from tests.unit.pipelex.plugins.linkup.test_data import LinkupExtractErrorHandlingTestData, LinkupSearchErrorHandlingTestData


def _make_linkup_extract_worker(mocker: MockerFixture) -> LinkupExtractWorker:
    """Create a minimal LinkupExtractWorker with mocked internals."""
    worker = object.__new__(LinkupExtractWorker)
    mock_model = mocker.MagicMock()
    mock_model.desc = "test-linkup-extract"
    mock_model.model_id = "linkup-fetch"
    mock_model.name = "linkup-fetch"
    worker.inference_model = mock_model

    mock_client = mocker.MagicMock()
    mock_client.async_fetch = mocker.AsyncMock()
    setattr(worker, "_linkup_client", mock_client)  # noqa: B010

    return worker


def _make_linkup_search_worker(mocker: MockerFixture) -> LinkupSearchWorker:
    """Create a minimal LinkupSearchWorker with mocked internals."""
    worker = object.__new__(LinkupSearchWorker)
    mock_model = mocker.MagicMock()
    mock_model.desc = "test-linkup-search"
    mock_model.model_id = "linkup/standard"
    mock_model.name = "linkup-standard"
    worker.inference_model = mock_model

    mock_client = mocker.MagicMock()
    mock_client.async_search = mocker.AsyncMock()
    setattr(worker, "_linkup_client", mock_client)  # noqa: B010

    return worker


def _get_linkup_client(worker: Any) -> Any:
    """Access the _linkup_client attribute via object.__getattribute__ to avoid linter complaints."""
    return worker._linkup_client  # noqa: SLF001


def _make_extract_job(mocker: MockerFixture) -> Any:
    """Create a mock ExtractJob for Linkup extract worker."""
    job = mocker.MagicMock()
    job.extract_input.document_uri = "https://example.com/page"
    job.extract_input.image_uri = None
    job.job_params.max_nb_images = None
    job.job_params.render_js = False
    job.job_params.include_raw_html = False
    job.job_report.extract_tokens_usage = None
    return job


def _make_search_job(mocker: MockerFixture) -> Any:
    """Create a mock SearchJob for Linkup search worker."""
    job = mocker.MagicMock()
    job.query = "test search query"
    job.job_params.search_setting.include_images = False
    job.job_params.search_setting.include_inline_citations = False
    job.job_params.search_setting.max_results = 10
    job.job_params.include_domains = None
    job.job_params.exclude_domains = None
    job.job_params.from_date = None
    job.job_params.to_date = None
    job.job_report.search_tokens_usage = None
    return job


@pytest.mark.asyncio(loop_scope="class")
class TestLinkupWorkerErrorHandling:
    """Tests for Linkup extract and search worker exception handling and error categorization."""

    # ---- Extract worker tests ----

    @pytest.mark.parametrize(
        ("_topic", "exception_class", "exception_message", "expected_category", "expected_message_substring"),
        LinkupExtractErrorHandlingTestData.EXTRACT_ERROR_CASES,
    )
    async def test_extract_error_categorization(
        self,
        mocker: MockerFixture,
        _topic: str,
        exception_class: type[Exception],
        exception_message: str,
        expected_category: InferenceErrorCategory,
        expected_message_substring: str,
    ) -> None:
        """Linkup extract errors are caught and categorized correctly."""
        worker = _make_linkup_extract_worker(mocker)
        sdk_exc = exception_class(exception_message)
        _get_linkup_client(worker).async_fetch.side_effect = sdk_exc

        with pytest.raises(ExtractJobFailureError) as exc_info:
            await worker._extract_pages(extract_job=_make_extract_job(mocker))  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is expected_category
        assert exc_info.value.__cause__ is sdk_exc
        assert expected_message_substring in exc_info.value.args[0].lower()

    # ---- Search worker tests ----

    @pytest.mark.parametrize(
        ("_topic", "exception_class", "exception_message", "expected_category", "expected_message_substring"),
        LinkupSearchErrorHandlingTestData.SEARCH_ERROR_CASES,
    )
    async def test_search_error_categorization(
        self,
        mocker: MockerFixture,
        _topic: str,
        exception_class: type[Exception],
        exception_message: str,
        expected_category: InferenceErrorCategory,
        expected_message_substring: str,
    ) -> None:
        """Linkup search errors are caught and categorized correctly."""
        worker = _make_linkup_search_worker(mocker)
        sdk_exc = exception_class(exception_message)
        _get_linkup_client(worker).async_search.side_effect = sdk_exc

        with pytest.raises(SearchJobFailureError) as exc_info:
            await worker._search_sourced_answer(search_job=_make_search_job(mocker))  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is expected_category
        assert exc_info.value.__cause__ is sdk_exc
        assert expected_message_substring in exc_info.value.args[0].lower()

    # ---- User action semantics ----

    @pytest.mark.parametrize(
        ("exception_class", "expected_kind"),
        [
            (LinkupAuthenticationError, UserActionKind.CHECK_CREDENTIALS),
            (LinkupInsufficientCreditError, UserActionKind.CHECK_BILLING),
            (LinkupTooManyRequestsError, UserActionKind.WAIT_AND_RETRY),
        ],
    )
    async def test_search_user_action_uses_specific_kind(
        self,
        mocker: MockerFixture,
        exception_class: type[Exception],
        expected_kind: UserActionKind,
    ) -> None:
        """Known Linkup error types carry a specific UserActionKind, not UNKNOWN."""
        worker = _make_linkup_search_worker(mocker)
        sdk_exc = exception_class("linkup error")
        _get_linkup_client(worker).async_search.side_effect = sdk_exc

        with pytest.raises(SearchJobFailureError) as exc_info:
            await worker._search_sourced_answer(search_job=_make_search_job(mocker))  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is expected_kind

    # ---- Error report tests ----

    async def test_extract_error_report_for_auth(self, mocker: MockerFixture) -> None:
        """to_error_report() for authentication error has CONFIGURATION category."""
        worker = _make_linkup_extract_worker(mocker)
        sdk_exc = LinkupAuthenticationError("Invalid API key")
        _get_linkup_client(worker).async_fetch.side_effect = sdk_exc

        with pytest.raises(ExtractJobFailureError) as exc_info:
            await worker._extract_pages(extract_job=_make_extract_job(mocker))  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        report = exc_info.value.to_error_report()
        assert report.error_category == "configuration"
        assert report.retryable is False
        assert report.error_type == "ExtractJobFailureError"

    async def test_search_error_report_for_rate_limit(self, mocker: MockerFixture) -> None:
        """to_error_report() for rate limit error has TRANSIENT category and is retryable."""
        worker = _make_linkup_search_worker(mocker)
        sdk_exc = LinkupTooManyRequestsError("Too many requests")
        _get_linkup_client(worker).async_search.side_effect = sdk_exc

        with pytest.raises(SearchJobFailureError) as exc_info:
            await worker._search_sourced_answer(search_job=_make_search_job(mocker))  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        report = exc_info.value.to_error_report()
        assert report.error_category == "transient"
        assert report.retryable is True
