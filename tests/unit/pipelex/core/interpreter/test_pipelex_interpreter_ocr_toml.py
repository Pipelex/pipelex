"""Test PipelexInterpreter OCR pipe to TOML string conversion."""

import pytest

from pipelex.core.interpreter import PipelexInterpreter
from pipelex.pipe_operators.ocr.pipe_ocr_blueprint import PipeOcrBlueprint


class TestPipelexInterpreterOcrToml:
    """Test OCR pipe to TOML string conversion."""

    @pytest.mark.parametrize(
        "pipe_name,blueprint,expected_toml",
        [
            # Basic OCR pipe
            (
                "extract_text",
                PipeOcrBlueprint(
                    type="PipeOcr",
                    definition="Extract text from document",
                    output="Page",
                ),
                """[pipe.extract_text]
type = "PipeOcr"
definition = "Extract text from document"
output = "Page\"""",
            ),
            # OCR pipe with inputs
            (
                "extract_with_input",
                PipeOcrBlueprint(
                    type="PipeOcr",
                    definition="Extract text from PDF",
                    inputs={"ocr_input": "PDF"},
                    output="Page",
                ),
                """[pipe.extract_with_input]
type = "PipeOcr"
definition = "Extract text from PDF"
inputs = { ocr_input = "PDF" }
output = "Page\"""",
            ),
        ],
    )
    def test_ocr_pipe_to_toml_string(self, pipe_name: str, blueprint: PipeOcrBlueprint, expected_toml: str):
        """Test converting OCR pipe blueprint to TOML string."""
        result = PipelexInterpreter.ocr_pipe_to_toml_string(pipe_name, blueprint, "test_domain")
        assert result == expected_toml
