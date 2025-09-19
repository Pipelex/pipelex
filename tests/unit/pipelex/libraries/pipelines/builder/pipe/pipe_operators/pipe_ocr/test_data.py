"""
Test data for PipeOcrBlueprint conversion tests.
"""

from typing import ClassVar, List, Tuple

from pipelex.core.pipes.pipe_input_spec_blueprint import (
    InputRequirementBlueprint as InputRequirementBlueprintCore,
)
from pipelex.libraries.pipelines.builder.pipe.inputs import InputRequirementBlueprint
from pipelex.libraries.pipelines.builder.pipe.pipe_ocr import PipeOcrBlueprint
from pipelex.pipe_operators.ocr.pipe_ocr_blueprint import PipeOcrBlueprint as PipeOcrBlueprintCore


class PipeOcrTestCases:
    """Test cases for PipeOcrBlueprint conversion."""

    SIMPLE_OCR = (
        "simple_ocr",
        PipeOcrBlueprint(
            definition="Extract text from image",
            inputs={"ocr_input": InputRequirementBlueprint(concept="Image")},
            output="ExtractedText",
            ocr_model="mistral-pixtral",
        ),
        "ocr_extractor",
        "test_domain",
        PipeOcrBlueprintCore(
            definition="Extract text from image",
            inputs={"ocr_input": InputRequirementBlueprintCore(concept="Image")},
            output="ExtractedText",
            type="PipeOcr",
            category="PipeOperator",
            ocr_model="mistral-pixtral",
        ),
    )

    OCR_WITH_OPTIONS = (
        "ocr_with_options",
        PipeOcrBlueprint(
            definition="OCR with page options",
            inputs={"ocr_input": InputRequirementBlueprint(concept="PDF")},
            output="PageContent",
            ocr_model="tesseract",
            page_images=True,
            page_image_captions=True,
            page_views=True,
            page_views_dpi=300,
        ),
        "advanced_ocr",
        "test_domain",
        PipeOcrBlueprintCore(
            definition="OCR with page options",
            inputs={"ocr_input": InputRequirementBlueprintCore(concept="PDF")},
            output="PageContent",
            type="PipeOcr",
            category="PipeOperator",
            ocr_model="tesseract",
        ),
    )

    TEST_CASES: ClassVar[List[Tuple[str, PipeOcrBlueprint, str, str, PipeOcrBlueprintCore]]] = [
        SIMPLE_OCR,
        OCR_WITH_OPTIONS,
    ]
