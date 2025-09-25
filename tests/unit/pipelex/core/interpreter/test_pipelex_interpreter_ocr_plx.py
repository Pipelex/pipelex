import pytest

from pipelex.core.interpreter import PipelexInterpreter
from pipelex.pipe_operators.ocr.pipe_ocr_blueprint import PipeOcrBlueprint


class TestPipelexInterpreterOcrPLX:
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
                    ocr="base_ocr_pypdfium2",
                ),
                """[pipe.extract_text]
type = "PipeOcr"
definition = "Extract text from document"
output = "Page"
ocr = "base_ocr_pypdfium2\"""",
            ),
            # OCR pipe with inputs
            (
                "extract_with_input",
                PipeOcrBlueprint(
                    type="PipeOcr",
                    definition="Extract text from PDF",
                    inputs={"ocr_input": "PDF"},
                    output="Page",
                    ocr="base_ocr_pypdfium2",
                ),
                """[pipe.extract_with_input]
type = "PipeOcr"
definition = "Extract text from PDF"
inputs = { ocr_input = "PDF" }
output = "Page"
ocr = "base_ocr_pypdfium2\"""",
            ),
        ],
    )
    def test_ocr_pipe_to_plx_string(self, pipe_name: str, blueprint: PipeOcrBlueprint, expected_plx: str):
        result = PipelexInterpreter.ocr_pipe_to_plx_string(pipe_name, blueprint)
        assert result == expected_plx
