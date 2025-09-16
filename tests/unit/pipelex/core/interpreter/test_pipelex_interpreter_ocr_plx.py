import pytest

from pipelex.cogt.ocr.ocr_handle import OcrHandle
from pipelex.core.interpreter import PipelexInterpreter
from pipelex.pipe_operators.ocr.pipe_ocr_blueprint import PipeOcrBlueprint


class TestPipelexInterpreterOcrPLX:
    """Test OCR pipe to PLX string conversion."""

    @pytest.mark.parametrize(
        "pipe_name,blueprint,expected_plx",
        [
            # Basic OCR pipe
            (
                "extract_text",
                PipeOcrBlueprint(
                    type="PipeOcr",
                    definition="Extract text from document",
                    output="Page",
                    ocr_handle=OcrHandle.BASIC_OCR,
                ),
                """[pipe.extract_text]
type = "PipeOcr"
definition = "Extract text from document"
output = "Page"
ocr_handle = "basic/pypdfium2\"""",
            ),
            # OCR pipe with inputs
            (
                "extract_with_input",
                PipeOcrBlueprint(
                    type="PipeOcr",
                    definition="Extract text from PDF",
                    inputs={"ocr_input": "PDF"},
                    output="Page",
                    ocr_handle=OcrHandle.BASIC_OCR,
                ),
                """[pipe.extract_with_input]
type = "PipeOcr"
definition = "Extract text from PDF"
inputs = { ocr_input = "PDF" }
output = "Page"
ocr_handle = "basic/pypdfium2\"""",
            ),
        ],
    )
    def test_ocr_pipe_to_plx_string(self, pipe_name: str, blueprint: PipeOcrBlueprint, expected_plx: str):
        """Test converting OCR pipe blueprint to PLX string."""
        result = PipelexInterpreter.ocr_pipe_to_plx_string(pipe_name, blueprint, "test_domain")
        assert result == expected_plx
