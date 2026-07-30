"""E2E tests for filename auto-population in ImageContent and DocumentContent."""

import pytest

from pipelex.core.stuffs.document_content import DocumentContent
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.pipeline.runner import PipelexMTHDSProtocol
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.urls import URLs
from tests.cases.documents import DocumentTestCases
from tests.cases.images import ImageTestCases

LIBRARY_DIRS = ["tests/e2e/pipelex/pipes/pipe_operators"]


@pytest.mark.llm
@pytest.mark.inference
@pytest.mark.dry_runnable
@pytest.mark.asyncio
class TestFilenameHtmlE2E:
    """E2E tests for filename in PipeCompose HTML template."""

    async def test_filename_in_compose_html(self, pipe_run_mode: PipeRunMode) -> None:
        """Test that $image.filename and $document.filename are rendered in composed HTML."""
        image_content = ImageContent(url=ImageTestCases.IMAGE_FILE_PATH_PNG_1)
        document_content = DocumentContent(url=DocumentTestCases.PDF_FILE_PATH_2)

        # Verify filename auto-population for local paths
        assert image_content.filename == "ai_lympics.png"
        assert document_content.filename == "Job-Offer.pdf"

        # Verify filename is NOT set for HTTP URLs
        assert ImageContent(url=URLs.png_example_1).filename is None
        assert DocumentContent(url=URLs.pdf_example_1).filename is None

        runner = PipelexMTHDSProtocol(
            library_dirs=LIBRARY_DIRS,
            pipe_run_mode=pipe_run_mode,
        )
        response = await runner.execute(
            pipe_code="describe_with_filenames_e2e",
            inputs={
                "image": image_content,
                "document": document_content,
            },
        )
        pipe_output = response.pipe_output

        assert pipe_output.main_stuff is not None
        if pipe_run_mode.is_live:
            result = pipe_output.main_stuff_as_html
            print(result)
            assert "ai_lympics.png" in result.inner_html
            assert "Job-Offer.pdf" in result.inner_html
