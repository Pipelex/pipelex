"""E2E tests for PipeExtract operator."""

import pytest

from pipelex import pretty_print
from pipelex.core.stuffs.document_content import DocumentContent
from pipelex.core.stuffs.page_content import PageContent
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipeline.runner import PipelexMTHDSProtocol
from tests.e2e.pipelex.pipes.pipe_operators.pipe_extract.test_data import PipeExtractTestCases

LIBRARY_DIRS = ["tests/e2e/pipelex/pipes/pipe_operators/pipe_extract"]


@pytest.mark.extract
@pytest.mark.inference
@pytest.mark.dry_runnable
@pytest.mark.asyncio(loop_scope="class")
class TestPipeExtract:
    """E2E tests for PipeExtract operator."""

    @pytest.mark.parametrize(("variant", "url"), PipeExtractTestCases.WEB_URL_CASES)
    async def test_extract_web_page(
        self,
        pipe_run_mode: PipeRunMode,
        variant: str,
        url: str,
    ) -> None:
        """Extract a web page via PipeExtract + linkup-fetch.

        Regression test for pre-flight URL validation: some sites (e.g. AllRecipes)
        bot-block HEAD requests with 403, and the pre-flight check must NOT abort
        the pipeline — the downstream extractor is the source of truth.
        """
        runner = PipelexMTHDSProtocol(
            library_dirs=LIBRARY_DIRS,
            pipe_run_mode=pipe_run_mode,
        )
        pipeline_response = await runner.execute(
            pipe_code="extract_web_page_e2e",
            inputs={
                "document": DocumentContent(url=url),
            },
        )

        pipe_output = pipeline_response.pipe_output
        assert pipe_output is not None
        assert pipe_output.working_memory is not None
        assert pipe_output.main_stuff is not None

        if pipe_run_mode.is_live:
            pages = pipe_output.main_stuff_as_items(item_type=PageContent)
            assert len(pages) > 0, f"Expected at least one page for {variant}"
            first_page = pages[0]
            page_text_content = first_page.text_and_images.text
            assert page_text_content is not None, f"Expected markdown text for {variant}"
            page_text = page_text_content.text
            assert len(page_text.strip()) > 0, f"Expected non-empty markdown text for {variant}"
            pretty_print(page_text[:500], title=f"Extracted markdown ({variant})")
