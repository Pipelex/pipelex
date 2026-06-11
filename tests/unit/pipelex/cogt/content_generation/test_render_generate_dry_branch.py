"""Unit tests for the ``run_mode == DRY`` branch in the page-view render leaf (render_generate).

The DRY branch sits above both the pypdfium2 rendering and the store step (eng review D10): a dry
run renders nothing and stores nothing, returning ``nb_extract_pages`` URL-only page-view mocks.
"""

import pytest
from pytest_mock import MockerFixture

from pipelex.cogt.content_generation.assignment_models import RenderPageViewsAssignment
from pipelex.cogt.content_generation.cogt_run_params import CogtRunParams
from pipelex.cogt.content_generation.render_generate import render_page_views_and_store
from pipelex.config import get_config
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipeline.job_metadata import JobMetadata


class TestRenderGenerateDryBranch:
    def _assignment(self, *, run_mode: PipeRunMode) -> RenderPageViewsAssignment:
        return RenderPageViewsAssignment(
            job_metadata=JobMetadata(user_id="u", pipeline_run_id="run_render_dry"),
            cogt_run_params=CogtRunParams(run_mode=run_mode),
            document_uri="file:///tmp/doc.pdf",
            page_views_dpi=72,
        )

    @pytest.mark.asyncio
    async def test_dry_mocks_page_views_without_rendering_or_storage(self, mocker: MockerFixture) -> None:
        """DRY: nb_extract_pages URL-only page-view mocks, no pdf rendering, no storage IO."""
        factory = mocker.MagicMock()

        page_views = await render_page_views_and_store(
            render_assignment=self._assignment(run_mode=PipeRunMode.DRY),
            generated_content_factory=factory,
        )

        factory.make_image_content.assert_not_called()
        assert len(page_views) == get_config().pipelex.dry_run_config.nb_extract_pages
        assert all(page_view.url for page_view in page_views)

    @pytest.mark.asyncio
    async def test_live_renders_and_stores(self, mocker: MockerFixture) -> None:
        """LIVE keeps the real path: pypdfium2 renders, factory stores each page view."""
        pil_image = mocker.MagicMock()
        mocker.patch(
            "pipelex.tools.pdf.pypdfium2_renderer.pypdfium2_renderer.render_pdf_pages_from_uri",
            new=mocker.AsyncMock(return_value=[pil_image, pil_image]),
        )
        mocker.patch(
            "pipelex.cogt.content_generation.render_generate.GeneratedImageRawDetails.make_from_pil_image",
            return_value=mocker.MagicMock(),
        )
        factory = mocker.MagicMock()
        factory.make_image_content = mocker.AsyncMock(return_value=mocker.MagicMock())

        page_views = await render_page_views_and_store(
            render_assignment=self._assignment(run_mode=PipeRunMode.LIVE),
            generated_content_factory=factory,
        )

        assert len(page_views) == 2
        assert factory.make_image_content.await_count == 2
