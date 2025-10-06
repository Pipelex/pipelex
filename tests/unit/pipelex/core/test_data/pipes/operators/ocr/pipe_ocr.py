from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.core.concepts.concept_native import NativeConceptCode
from pipelex.pipe_operators.ocr.pipe_ocr_blueprint import PipeOcrBlueprint

PIPE_OCR = (
    "pipe_ocr",
    """domain = "test_pipes"
description = "Domain with OCR pipe"

[pipe.extract_text]
type = "PipeOcr"
description = "Extract text from document"
output = "Page"
ocr = "base_ocr_pypdfium2"
""",
    PipelexBundleBlueprint(
        domain="test_pipes",
        description="Domain with OCR pipe",
        pipe={
            "extract_text": PipeOcrBlueprint(
                type="PipeOcr",
                description="Extract text from document",
                output=NativeConceptCode.PAGE,
                ocr="base_ocr_pypdfium2",
            ),
        },
    ),
)

# Export all PipeOcr test cases
PIPE_OCR_TEST_CASES = [
    PIPE_OCR,
]
