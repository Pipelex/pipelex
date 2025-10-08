from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.core.concepts.concept_native import NativeConceptCode
from pipelex.pipe_operators.extract.pipe_extract_blueprint import PipeExtractBlueprint

PIPE_EXTRACT = (
    "pipe_extract",
    """domain = "test_pipes"
description = "Domain with extract pipe"

[pipe.extract_text]
type = "PipeExtract"
description = "Extract text from document"
output = "Page"
model = "base_extract_pypdfium2"
""",
    PipelexBundleBlueprint(
        domain="test_pipes",
        description="Domain with extract pipe",
        pipe={
            "extract_text": PipeExtractBlueprint(
                type="PipeExtract",
                description="Extract text from document",
                output=NativeConceptCode.PAGE,
                model="base_extract_pypdfium2",
            ),
        },
    ),
)

# Export all PipeExtract test cases
PIPE_EXTRACT_TEST_CASES = [
    PIPE_EXTRACT,
]
