"""Tests for Linkup search worker provider_metadata + semantic UserActionKind."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from linkup import (
    LinkupAuthenticationError,
    LinkupInsufficientCreditError,
    LinkupInvalidRequestError,
    LinkupNoResultError,
    LinkupTimeoutError,
    LinkupTooManyRequestsError,
    LinkupUnknownError,
)

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

from pipelex.cogt.exceptions import InferenceErrorCategory, SearchJobFailureError
from pipelex.cogt.inference.error_classification import UserActionKind
from pipelex.plugins.linkup.linkup_search_worker import LinkupSearchWorker


def _make_worker(mocker: MockerFixture) -> LinkupSearchWorker:
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


def _make_search_job(mocker: MockerFixture) -> Any:
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
class TestLinkupSearchWorkerSemantic:
    """Each Linkup SDK exception branch carries semantic UserActionKind + provider_metadata."""

    @pytest.mark.parametrize(
        ("exception_class", "expected_category", "expected_kind"),
        [
            (LinkupAuthenticationError, InferenceErrorCategory.CONFIGURATION, UserActionKind.CHECK_CREDENTIALS),
            (LinkupInsufficientCreditError, InferenceErrorCategory.CAPACITY, UserActionKind.CHECK_BILLING),
            (LinkupTooManyRequestsError, InferenceErrorCategory.TRANSIENT, UserActionKind.WAIT_AND_RETRY),
            (LinkupTimeoutError, InferenceErrorCategory.TRANSIENT, UserActionKind.WAIT_AND_RETRY),
            (LinkupInvalidRequestError, InferenceErrorCategory.CONTENT, UserActionKind.CHANGE_INPUT),
            (LinkupNoResultError, InferenceErrorCategory.CONTENT, UserActionKind.CHANGE_INPUT),
            (LinkupUnknownError, InferenceErrorCategory.TRANSIENT, UserActionKind.WAIT_AND_RETRY),
        ],
    )
    async def test_linkup_error_carries_semantic_user_action(
        self,
        mocker: MockerFixture,
        exception_class: type[Exception],
        expected_category: InferenceErrorCategory,
        expected_kind: UserActionKind,
    ) -> None:
        worker = _make_worker(mocker)
        sdk_exc = exception_class(f"{exception_class.__name__} happened")
        client: Any = getattr(worker, "_linkup_client")  # noqa: B009
        client.async_search.side_effect = sdk_exc

        with pytest.raises(SearchJobFailureError) as exc_info:
            await worker._search_sourced_answer(search_job=_make_search_job(mocker))  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is expected_category
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is expected_kind
        assert exc_info.value.provider_metadata is not None
        assert exc_info.value.provider_metadata.provider == "linkup"
        assert exc_info.value.provider_metadata.sdk_exception_type == exception_class.__name__
        assert exc_info.value.provider_metadata.provider_error_code == exception_class.__name__
        assert exc_info.value.provider_metadata.status_code is None
        assert exc_info.value.__cause__ is sdk_exc
