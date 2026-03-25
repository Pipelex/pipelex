from typing import ClassVar

from pipelex.builder.pipe.pipe_extract_spec import PipeExtractSpec
from pipelex.pipe_operators.extract.pipe_extract_blueprint import PipeExtractBlueprint


class PipeExtractTestCases:
    SIMPLE_EXTRACT = (
        "simple_extract",
        PipeExtractSpec(
            pipe_code="extractor",
            description="Extract text from image",
            inputs={"image": "Image"},
            output="Page",
            model="@default-text-from-pdf",
        ),
        PipeExtractBlueprint(
            source=None,
            description="Extract text from image",
            inputs={"image": "Image"},
            output="Page[]",
            model="@default-text-from-pdf",
        ),
    )

    EXTRACT_WITH_OPTIONS = (
        "extract_with_options",
        PipeExtractSpec(
            pipe_code="advanced_extract",
            description="Extract with page options",
            inputs={"document": "Document"},
            output="Page[]",
            model="@default-text-from-pdf",
            max_page_images=None,
            page_views=True,
        ),
        PipeExtractBlueprint(
            source=None,
            description="Extract with page options",
            inputs={"document": "Document"},
            output="Page[]",
            model="@default-text-from-pdf",
            max_page_images=None,
            page_image_captions=None,
            page_views=True,
            page_views_dpi=None,
        ),
    )

    TEST_CASES: ClassVar[list[tuple[str, PipeExtractSpec, PipeExtractBlueprint]]] = [
        SIMPLE_EXTRACT,
        EXTRACT_WITH_OPTIONS,
    ]
