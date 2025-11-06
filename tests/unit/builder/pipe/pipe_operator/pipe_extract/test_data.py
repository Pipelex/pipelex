from typing import ClassVar

from pipelex.builder.pipe.pipe_extract_spec import ExtractSkill, PipeExtractSpec
from pipelex.pipe_operators.extract.pipe_extract_blueprint import PipeExtractBlueprint


class PipeExtractTestCases:
    SIMPLE_EXTRACT = (
        "simple_extract",
        PipeExtractSpec(
            pipe_code="extractor",
            description="Extract text from image",
            inputs={"image": "Image"},
            output="Page",
            extract_skill=ExtractSkill.EXTRACT_TEXT_FROM_VISUALS,
        ),
        PipeExtractBlueprint(
            source=None,
            description="Extract text from image",
            inputs={"image": "Image"},
            output="Page",
            type="PipeExtract",
            pipe_category="PipeOperator",
            model=ExtractSkill.EXTRACT_TEXT_FROM_VISUALS,
        ),
    )

    EXTRACT_WITH_OPTIONS = (
        "extract_with_options",
        PipeExtractSpec(
            pipe_code="advanced_extract",
            description="Extract with page options",
            inputs={"document": "PDF"},
            output="Page",
            extract_skill=ExtractSkill.EXTRACT_TEXT_FROM_PDF,
            page_images=True,
            page_image_captions=True,
            page_views=True,
        ),
        PipeExtractBlueprint(
            source=None,
            description="Extract with page options",
            inputs={"document": "PDF"},
            output="Page",
            type="PipeExtract",
            pipe_category="PipeOperator",
            model=ExtractSkill.EXTRACT_TEXT_FROM_PDF,
            page_images=True,
            page_image_captions=True,
            page_views=True,
            page_views_dpi=None,
        ),
    )

    TEST_CASES: ClassVar[list[tuple[str, PipeExtractSpec, PipeExtractBlueprint]]] = [
        SIMPLE_EXTRACT,
        EXTRACT_WITH_OPTIONS,
    ]
