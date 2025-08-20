"""PipeOcr test cases."""

from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.pipe_operators.pipe_ocr_factory import PipeOcrBlueprint

PIPE_OCR = (
    "pipe_ocr",
    """domain = "test_pipes"
definition = "Domain with OCR pipe"

[pipe.extract_text]
type = "PipeOcr"
definition = "Extract text from document"
output = "Page"
""",
    PipelexBundleBlueprint(
        domain="test_pipes",
        definition="Domain with OCR pipe",
        pipe={
            "extract_text": PipeOcrBlueprint(
                type="PipeOcr",
                definition="Extract text from document",
                output="Page",
            ),
        },
    ),
)

# Export all PipeOcr test cases
PIPE_OCR_TEST_CASES = [
    PIPE_OCR,
]
