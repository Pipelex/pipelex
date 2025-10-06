from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.core.concepts.concept_native import NativeConceptCode
from pipelex.pipe_operators.extract.pipe_extract_blueprint import PipeExtractBlueprint

PIPE_OCR = (
    "pipe_ocr",
    """domain = "test_pipes"
description = "Domain with OCR pipe"

[pipe.extract_text]
type = "PipeExtract"
description = "Extract text from document"
output = "Page"
ocr = "base_extract_pypdfium2"
""",
    PipelexBundleBlueprint(
        domain="test_pipes",
        description="Domain with OCR pipe",
        pipe={
            "extract_text": PipeExtractBlueprint(
                type="PipeExtract",
                description="Extract text from document",
                output=NativeConceptCode.PAGE,
                ocr="base_extract_pypdfium2",
            ),
        },
    ),
)

# Export all PipeExtract test cases
PIPE_OCR_TEST_CASES = [
    PIPE_OCR,
]
