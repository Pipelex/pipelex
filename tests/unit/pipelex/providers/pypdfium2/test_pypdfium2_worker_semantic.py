"""Tests for pypdfium2 extract worker provider_metadata + semantic UserActionKind."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

from pipelex.cogt.exceptions import ExtractJobFailureError, InferenceErrorCategory
from pipelex.cogt.inference.error_classification import UserActionKind
from pipelex.providers.pypdfium2.pypdfium2_worker import Pypdfium2Worker


def _make_worker(mocker: MockerFixture) -> Pypdfium2Worker:
    worker = object.__new__(Pypdfium2Worker)
    mock_model = mocker.MagicMock()
    mock_model.desc = "test-pypdfium2"
    mock_model.model_id = "pypdfium2"
    mock_model.name = "pypdfium2"
    worker.inference_model = mock_model
    return worker


def _make_extract_job(mocker: MockerFixture) -> Any:
    job = mocker.MagicMock()
    job.extract_input.image_uri = None
    job.extract_input.document_uri = "/tmp/test.pdf"  # ruff: ignore[hardcoded-temp-file]
    job.job_params.max_nb_images = 0
    job.job_report.extract_tokens_usage = None
    return job


@pytest.mark.asyncio(loop_scope="class")
class TestPypdfium2WorkerSemantic:
    """Each pypdfium2 exception branch carries semantic UserActionKind + provider_metadata."""

    @pytest.mark.parametrize(
        ("exception_class", "exception_message", "expected_category", "expected_kind"),
        [
            (FileNotFoundError, "No such file", InferenceErrorCategory.CONTENT, UserActionKind.CHANGE_INPUT),
            (ValueError, "Invalid PDF", InferenceErrorCategory.CONTENT, UserActionKind.CHANGE_INPUT),
            (RuntimeError, "PDF parsing failed", InferenceErrorCategory.CONTENT, UserActionKind.CHANGE_INPUT),
            (OSError, "Disk read error", InferenceErrorCategory.TRANSIENT, UserActionKind.WAIT_AND_RETRY),
        ],
    )
    async def test_local_exception_carries_semantic_user_action(
        self,
        mocker: MockerFixture,
        exception_class: type[Exception],
        exception_message: str,
        expected_category: InferenceErrorCategory,
        expected_kind: UserActionKind,
    ) -> None:
        worker = _make_worker(mocker)
        sdk_exc = exception_class(exception_message)

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

        assert exc_info.value.error_category is expected_category
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is expected_kind
        assert exc_info.value.provider_metadata is not None
        assert exc_info.value.provider_metadata.provider == "pypdfium2"
        assert exc_info.value.provider_metadata.sdk_exception_type == exception_class.__name__
        assert exc_info.value.provider_metadata.provider_error_code == exception_class.__name__
        assert exc_info.value.provider_metadata.status_code is None
        assert exc_info.value.__cause__ is sdk_exc
