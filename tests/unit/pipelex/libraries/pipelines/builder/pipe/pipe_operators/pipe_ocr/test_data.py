from typing import ClassVar

from pipelex.core.pipes.pipe_input_blueprint import InputRequirementBlueprint

from pipelex.libraries.pipelines.builder.pipe.pipe_ocr_spec import PipeOcrSpec
from pipelex.pipe_operators.ocr.pipe_ocr_blueprint import PipeOcrBlueprint


class PipeOcrTestCases:
    SIMPLE_OCR = (
        "simple_ocr",
        PipeOcrSpec(
            the_pipe_code="ocr_extractor",
            definition="Extract text from image",
            inputs={"image": "Image"},
            output="ExtractedText",
            ocr="extract_text_from_visuals",
        ),
        PipeOcrBlueprint(
            source=None,
            definition="Extract text from image",
            inputs={"image": InputRequirementBlueprint(concept="Image")},
            output="ExtractedText",
            type="PipeOcr",
            category="PipeOperator",
            ocr="base_ocr_mistral",
        ),
    )

    OCR_WITH_OPTIONS = (
        "ocr_with_options",
        PipeOcrSpec(
            the_pipe_code="advanced_ocr",
            definition="OCR with page options",
            inputs={"document": "PDF"},
            output="PageContent",
            ocr="extract_text_from_pdf",
            page_images=True,
            page_image_captions=True,
            page_views=True,
        ),
        PipeOcrBlueprint(
            source=None,
            definition="OCR with page options",
            inputs={"document": InputRequirementBlueprint(concept="PDF")},
            output="PageContent",
            type="PipeOcr",
            category="PipeOperator",
            ocr="base_ocr_mistral",
            page_images=True,
            page_image_captions=True,
            page_views=True,
            page_views_dpi=None,
        ),
    )

    TEST_CASES: ClassVar[list[tuple[str, PipeOcrSpec, PipeOcrBlueprint]]] = [
        SIMPLE_OCR,
        OCR_WITH_OPTIONS,
    ]
