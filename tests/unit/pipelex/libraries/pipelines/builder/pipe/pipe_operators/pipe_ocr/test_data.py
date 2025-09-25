from typing import ClassVar

from pipelex.core.pipes.pipe_input_blueprint import InputRequirementBlueprint
from pipelex.libraries.pipelines.builder.pipe.inputs_spec import InputRequirementSpec
from pipelex.libraries.pipelines.builder.pipe.pipe_ocr_spec import PipeOcrSpec
from pipelex.pipe_operators.ocr.pipe_ocr_blueprint import PipeOcrBlueprint


class PipeOcrTestCases:
    SIMPLE_OCR = (
        "simple_ocr",
        PipeOcrSpec(
            the_pipe_code="ocr_extractor",
            definition="Extract text from image",
            inputs={"ocr_input": InputRequirementSpec(concept="Image")},
            output="ExtractedText",
            ocr="mistral-pixtral",
        ),
        PipeOcrBlueprint(
            definition="Extract text from image",
            inputs={"ocr_input": InputRequirementBlueprint(concept="Image")},
            output="ExtractedText",
            type="PipeOcr",
            category="PipeOperator",
            ocr="mistral-pixtral",
        ),
    )

    OCR_WITH_OPTIONS = (
        "ocr_with_options",
        PipeOcrSpec(
            the_pipe_code="advanced_ocr",
            definition="OCR with page options",
            inputs={"ocr_input": InputRequirementSpec(concept="PDF")},
            output="PageContent",
            ocr="tesseract",
            page_images=True,
            page_image_captions=True,
            page_views=True,
            page_views_dpi=300,
        ),
        PipeOcrBlueprint(
            definition="OCR with page options",
            inputs={"ocr_input": InputRequirementBlueprint(concept="PDF")},
            output="PageContent",
            type="PipeOcr",
            category="PipeOperator",
            ocr="tesseract",
        ),
    )

    TEST_CASES: ClassVar[list[tuple[str, PipeOcrSpec, PipeOcrBlueprint]]] = [
        SIMPLE_OCR,
        OCR_WITH_OPTIONS,
    ]
