import pytest

from pipelex.tools.pdf.pypdfium2_renderer import pypdfium2_renderer
from tests.test_data import PDFTestCases


@pytest.mark.asyncio(loop_scope="class")
class TestPDF:
    @pytest.mark.parametrize("file_path", PDFTestCases.DOCUMENT_FILE_PATHS)
    async def test_pdf_path_to_images(self, file_path: str):
        images = await pypdfium2_renderer.render_pdf_pages(file_path)
        assert len(images) > 0
