"""PipeOcr test cases."""

from pipelex.cogt.ocr.ocr_handle import OcrHandle
from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.core.concepts.concept_native import NativeConceptEnum
from pipelex.pipe_operators.ocr.pipe_ocr_blueprint import PipeOcrBlueprint

PIPE_OCR = (
    "pipe_ocr",
    """domain = "test_pipes"
definition = "Domain with OCR pipe"

[pipe.extract_text]
type = "PipeOcr"
definition = "Extract text from document"
output = "Page"
ocr_handle = "basic/pypdfium2"
""",
    PipelexBundleBlueprint(
        domain="test_pipes",
        definition="Domain with OCR pipe",
        pipe={
            "extract_text": PipeOcrBlueprint(
                type="PipeOcr",
                definition="Extract text from document",
                output=NativeConceptEnum.PAGE.value,
                ocr_handle=OcrHandle.BASIC_OCR,
            ),
        },
    ),
)

# Export all PipeOcr test cases
PIPE_OCR_TEST_CASES = [
    PIPE_OCR,
]
