from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.mthds_parsing.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.pipe_operators.extract.pipe_extract_blueprint import PipeExtractBlueprint

PIPE_EXTRACT = (
    "pipe_extract",
    """domain = "test_pipes"
description = "Domain with extract pipe"

[pipe.extract_text]
type = "PipeExtract"
description = "Extract text from document"
inputs = { document = "Document" }
output = "Page[]"
model = "$extract-testing"
""",
    PipelexBundleBlueprint(
        domain="test_pipes",
        description="Domain with extract pipe",
        pipe={
            "extract_text": PipeExtractBlueprint(
                type="PipeExtract",
                description="Extract text from document",
                inputs={
                    "document": NativeConceptCode.DOCUMENT,
                },
                output=NativeConceptCode.PAGE.as_output_multiple_indeterminate,
                model="$extract-testing",
            ),
        },
    ),
)

# Export all PipeExtract test cases
PIPE_EXTRACT_TEST_CASES = [
    PIPE_EXTRACT,
]
