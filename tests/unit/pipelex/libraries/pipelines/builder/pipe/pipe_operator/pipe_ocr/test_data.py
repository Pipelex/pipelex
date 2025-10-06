from typing import ClassVar

from pipelex.core.pipes.input_requirement_blueprint import InputRequirementBlueprint
from pipelex.libraries.pipelines.builder.pipe.pipe_extract_spec import PipeExtractSpec
from pipelex.pipe_operators.extract.pipe_extract_blueprint import PipeExtractBlueprint


class PipeExtractTestCases:
    SIMPLE_OCR = (
        "simple_ocr",
        PipeExtractSpec(
            pipe_code="ocr_extractor",
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
            category="PipeOperator",
            ocr="base_ocr_mistral",
        ),
    )

    OCR_WITH_OPTIONS = (
        "ocr_with_options",
        PipeExtractSpec(
            pipe_code="advanced_ocr",
            description="OCR with page options",
            inputs={"document": "PDF"},
            output="PageContent",
            extract_skill="extract_text_from_pdf",
            page_images=True,
            page_image_captions=True,
            page_views=True,
        ),
        PipeExtractBlueprint(
            source=None,
            description="OCR with page options",
            inputs={"document": InputRequirementBlueprint(concept="PDF")},
            output="PageContent",
            type="PipeExtract",
            category="PipeOperator",
            ocr="base_ocr_mistral",
            page_images=True,
            page_image_captions=True,
            page_views=True,
            page_views_dpi=None,
        ),
    )

    TEST_CASES: ClassVar[list[tuple[str, PipeExtractSpec, PipeExtractBlueprint]]] = [
        SIMPLE_OCR,
        OCR_WITH_OPTIONS,
    ]
