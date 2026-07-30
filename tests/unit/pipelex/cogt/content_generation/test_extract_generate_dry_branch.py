"""Unit tests for the ``run_mode == DRY`` branch in the extract leaf (extract_generate).

The DRY branch sits at the ``*_and_store`` layer, ABOVE the raw provider leaf (eng review D10):
a dry run must perform no provider call and no storage IO. Contract: under DRY the worker and the
``GeneratedContentFactory`` are never touched, a document mocks ``nb_extract_pages`` synthetic
pages while an image mocks exactly one, and LIVE keeps the real extract-and-store path.
"""

import pytest
from pytest_mock import MockerFixture

from pipelex.cogt.content_generation.assignment_models import ExtractAssignment
from pipelex.cogt.content_generation.cogt_run_params import CogtRunParams
from pipelex.cogt.content_generation.extract_generate import extract_gen_pages_and_store
from pipelex.cogt.extract.extract_input import ExtractInput
from pipelex.cogt.extract.extract_job_components import ExtractJobConfig, ExtractJobParams
from pipelex.config import get_config
from pipelex.system.job_metadata import JobMetadata
from pipelex.system.pipe_run_mode import PipeRunMode


class TestExtractGenerateDryBranch:
    def _assignment(self, *, run_mode: PipeRunMode, extract_input: ExtractInput) -> ExtractAssignment:
        return ExtractAssignment(
            job_metadata=JobMetadata(user_id="u", pipeline_run_id="run_extract_dry"),
            cogt_run_params=CogtRunParams(run_mode=run_mode),
            extract_handle="mock-extract-handle",
            extract_input=extract_input,
            extract_job_params=ExtractJobParams.make_default_extract_job_params(),
            extract_job_config=ExtractJobConfig(),
        )

    @pytest.mark.asyncio
    async def test_dry_document_mocks_pages_without_io(self, mocker: MockerFixture) -> None:
        """DRY on a document: nb_extract_pages synthetic pages, no provider call, no storage IO."""
        worker_spy = mocker.patch("pipelex.cogt.content_generation.extract_generate.get_extract_worker")
        factory = mocker.MagicMock()

        page_contents = await extract_gen_pages_and_store(
            extract_assignment=self._assignment(run_mode=PipeRunMode.DRY, extract_input=ExtractInput(document_uri="file:///tmp/doc.pdf")),
            generated_content_factory=factory,
        )

        worker_spy.assert_not_called()
        factory.make_page_contents.assert_not_called()
        assert len(page_contents) == get_config().pipelex.dry_run_config.nb_extract_pages
        for page_content in page_contents:
            assert page_content.text_and_images.text is not None
            assert page_content.text_and_images.text.text.startswith("DRY RUN:")

    @pytest.mark.asyncio
    async def test_dry_image_mocks_single_page(self, mocker: MockerFixture) -> None:
        """DRY on an image input mocks exactly one page."""
        mocker.patch("pipelex.cogt.content_generation.extract_generate.get_extract_worker")
        factory = mocker.MagicMock()

        page_contents = await extract_gen_pages_and_store(
            extract_assignment=self._assignment(run_mode=PipeRunMode.DRY, extract_input=ExtractInput(image_uri="file:///tmp/scan.png")),
            generated_content_factory=factory,
        )

        assert len(page_contents) == 1

    @pytest.mark.asyncio
    async def test_live_runs_provider_and_stores(self, mocker: MockerFixture) -> None:
        """LIVE keeps the real path: provider extracts, factory stores."""
        sentinel_output = mocker.MagicMock()
        worker = mocker.MagicMock()
        worker.extract_pages = mocker.AsyncMock(return_value=sentinel_output)
        mocker.patch("pipelex.cogt.content_generation.extract_generate.get_extract_worker", return_value=worker)
        mocker.patch("pipelex.cogt.content_generation.extract_generate.ExtractJobFactory.make_extract_job", return_value=mocker.MagicMock())
        factory = mocker.MagicMock()
        factory.make_page_contents = mocker.AsyncMock(return_value=[])

        await extract_gen_pages_and_store(
            extract_assignment=self._assignment(run_mode=PipeRunMode.LIVE, extract_input=ExtractInput(document_uri="file:///tmp/doc.pdf")),
            generated_content_factory=factory,
        )

        worker.extract_pages.assert_awaited_once()
        factory.make_page_contents.assert_awaited_once()
