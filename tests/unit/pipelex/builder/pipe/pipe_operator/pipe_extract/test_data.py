from typing import ClassVar

from pipelex.builder.pipe.pipe_extract_spec import PipeExtractSpec
from pipelex.core.pipes.input_requirement_blueprint import InputRequirementBlueprint
from pipelex.pipe_operators.extract.pipe_extract_blueprint import PipeExtractBlueprint


class PipeExtractTestCases:
    SIMPLE_EXTRACT = (
        "simple_extract",
        PipeExtractSpec(
            pipe_code="extractor",
            description="Extract text from image",
            inputs={"image": "Image"},
            output="ExtractedText",
            extract_skill="extract_text_from_visuals",
        ),
        PipeExtractBlueprint(
            source=None,
            description="Extract text from image",
            inputs={"image": InputRequirementBlueprint(concept="Image")},
            output="ExtractedText",
            type="PipeExtract",
            pipe_category="PipeOperator",
            model="base_ocr_mistral",
        ),
    )

    EXTRACT_WITH_OPTIONS = (
        "extract_with_options",
        PipeExtractSpec(
            pipe_code="advanced_extract",
            description="Extract with page options",
            inputs={"document": "PDF"},
            output="PageContent",
            extract_skill="extract_text_from_pdf",
            page_images=True,
            page_image_captions=True,
            page_views=True,
        ),
        PipeExtractBlueprint(
            source=None,
            description="Extract with page options",
            inputs={"document": InputRequirementBlueprint(concept="PDF")},
            output="PageContent",
            type="PipeExtract",
            pipe_category="PipeOperator",
            model="base_ocr_mistral",
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
