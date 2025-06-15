import pytest

from pipelex.tools.pdf.pypdfium2_renderer import pypdfium2_renderer
from tests.test_data import PDFTestCases


@pytest.mark.asyncio(loop_scope="class")
class TestPdfRender:
    @pytest.mark.parametrize("file_path", PDFTestCases.DOCUMENT_FILE_PATHS)
    async def test_render_pdf_from_path(self, file_path: str):
        images = await pypdfium2_renderer.render_pdf_pages(pdf_input=file_path, dpi=72)
        assert len(images) > 0
