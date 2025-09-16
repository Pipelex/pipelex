import pytest

from pipelex import pretty_print
from pipelex.tools.pdf.pypdfium2_renderer import pypdfium2_renderer
from tests.cases import PDFTestCases


@pytest.mark.asyncio(loop_scope="class")
class TestPdfRender:
    @pytest.mark.parametrize("file_path", PDFTestCases.DOCUMENT_FILE_PATHS)
    async def test_render_pdf_from_path(self, file_path: str):
        images = await pypdfium2_renderer.render_pdf_pages(pdf_input=file_path, dpi=72)
        assert len(images) > 0

    # pytest -k test_get_text_from_pdf_pages -s -vv
    @pytest.mark.parametrize("file_path", PDFTestCases.DOCUMENT_FILE_PATHS)
    async def test_get_text_from_pdf_pages(
        self,
        pytestconfig: pytest.Config,
        file_path: str,
    ):
        texts = await pypdfium2_renderer.get_text_from_pdf_pages(pdf_input=file_path)
        assert len(texts) > 0
        assert all(isinstance(text, str) for text in texts)
        if pytestconfig.get_verbosity() >= 2:
            full_text = "\n".join(texts)
            print("\n")
            pretty_print(full_text, title=f"Full text from pdf '{file_path}'")
