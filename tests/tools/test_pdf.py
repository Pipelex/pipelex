import pytest

from pipelex import pretty_print
from pipelex.tools.config.manager import config_manager
from pipelex.tools.misc.utilities import cleanup_name_to_pascal_case, get_package_name
from pipelex.tools.pdf.pdf_render import render_pdf_pages
from tests.cogt.test_data import OCRTestCases


class TestPDF:
    @pytest.mark.parametrize("file_path", [OCRTestCases.DOCUMENT_FILE_PATH])
    def test_pdf_path_to_images(self, file_path: str):
        images = render_pdf_pages(file_path)
        assert len(images) == 1
