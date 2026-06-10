"""Unit tests for the ``is_mock_inference`` hard guard in the extract leaf (extract_generate).

``--mock-inference`` has no leaf-level mock for document extraction, so reaching the extract leaf under
the flag would dispatch to the real provider and spend. The leaf must fail loud instead: raise
``MockInferenceUnsupportedError`` before ``get_extract_worker`` is ever called. With the flag off, the
real worker path runs unchanged — proving the guard is keyed strictly on ``cogt_run_params.is_mock_inference``.
"""

import pytest
from pytest_mock import MockerFixture

from pipelex.cogt.content_generation.assignment_models import ExtractAssignment
from pipelex.cogt.content_generation.cogt_run_params import CogtRunParams
from pipelex.cogt.content_generation.exceptions import MockInferenceUnsupportedError
from pipelex.cogt.content_generation.extract_generate import extract_gen_pages
from pipelex.cogt.extract.extract_input import ExtractInput
from pipelex.cogt.extract.extract_job_components import ExtractJobConfig, ExtractJobParams
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipeline.job_metadata import JobMetadata


class TestExtractGenerateMockGuard:
    def _assignment(self, *, is_mock_inference: bool) -> ExtractAssignment:
        return ExtractAssignment(
            job_metadata=JobMetadata(user_id="u", pipeline_run_id="run_extract_guard"),
            cogt_run_params=CogtRunParams(run_mode=PipeRunMode.LIVE, is_mock_inference=is_mock_inference),
            extract_handle="mock-extract-handle",
            extract_input=ExtractInput(document_uri="file:///tmp/doc.pdf"),
            extract_job_params=ExtractJobParams(
                max_nb_images=None,
                image_min_size=None,
                should_caption_images=False,
                should_include_page_views=False,
                page_views_dpi=None,
            ),
            extract_job_config=ExtractJobConfig(),
        )

    @pytest.mark.asyncio
    async def test_mock_flag_raises_and_skips_worker(self, mocker: MockerFixture) -> None:
        """is_mock_inference=True -> the leaf raises before any provider call (get_extract_worker untouched)."""
        worker_spy = mocker.patch("pipelex.cogt.content_generation.extract_generate.get_extract_worker")

        with pytest.raises(MockInferenceUnsupportedError):
            await extract_gen_pages(self._assignment(is_mock_inference=True))

        worker_spy.assert_not_called()  # no provider call -> no spend

    @pytest.mark.asyncio
    async def test_no_flag_uses_real_worker(self, mocker: MockerFixture) -> None:
        """is_mock_inference=False -> the real worker path runs (get_extract_worker is called)."""
        sentinel = mocker.MagicMock()
        worker = mocker.MagicMock()
        worker.extract_pages = mocker.AsyncMock(return_value=sentinel)
        worker_spy = mocker.patch("pipelex.cogt.content_generation.extract_generate.get_extract_worker", return_value=worker)
        mocker.patch("pipelex.cogt.content_generation.extract_generate.ExtractJobFactory.make_extract_job", return_value=mocker.MagicMock())

        result = await extract_gen_pages(self._assignment(is_mock_inference=False))

        worker_spy.assert_called_once()
        assert result is sentinel
