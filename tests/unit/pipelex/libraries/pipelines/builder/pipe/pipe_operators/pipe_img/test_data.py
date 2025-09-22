"""
Test data for PipeImgGenBlueprint conversion tests.
"""

from typing import ClassVar, List, Tuple

from pipelex.cogt.img_gen.img_gen_job_components import AspectRatio, Quality
from pipelex.core.pipes.pipe_input_spec_blueprint import (
    InputRequirementBlueprint as InputRequirementBlueprintCore,
)
from pipelex.libraries.pipelines.builder.pipe.inputs import InputRequirementBlueprint
from pipelex.libraries.pipelines.builder.pipe.pipe_img import PipeImgGenBlueprint
from pipelex.pipe_operators.img_gen.pipe_img_gen_blueprint import (
    PipeImgGenBlueprint as PipeImgGenBlueprintCore,
)


class PipeImgGenTestCases:
    """Test cases for PipeImgGenBlueprint conversion."""

    SIMPLE_IMG_GEN = (
        "simple_img_gen",
        PipeImgGenBlueprint(
            definition="Generate an image",
            inputs={},
            output="GeneratedImage",
            img_gen_prompt="A beautiful sunset over mountains",
        ),
        "img_generator",
        "test_domain",
        PipeImgGenBlueprintCore(
            definition="Generate an image",
            inputs=None,
            output="GeneratedImage",
            type="PipeImgGen",
            category="PipeOperator",
            img_gen_prompt="A beautiful sunset over mountains",
            img_gen=None,
            aspect_ratio=None,
            background=None,
            output_format=None,
            nb_output=None,
            is_raw=None,
            seed=None,
            img_gen_prompt_var_name=None,
        ),
    )

    IMG_GEN_WITH_OPTIONS = (
        "img_gen_with_options",
        PipeImgGenBlueprint(
            definition="Generate image with options",
            inputs={"description": InputRequirementBlueprint(concept="Text")},
            output="Image",
            img_gen="gpt-image-1",
            aspect_ratio=AspectRatio.SQUARE,
            seed=42,
            nb_output=3,
        ),
        "advanced_img_gen",
        "test_domain",
        PipeImgGenBlueprintCore(
            definition="Generate image with options",
            inputs={"description": InputRequirementBlueprintCore(concept="Text")},
            output="Image",
            type="PipeImgGen",
            category="PipeOperator",
            img_gen_prompt=None,
            img_gen="gpt-image-1",
            aspect_ratio=AspectRatio.SQUARE,
            background=None,
            output_format=None,
            is_raw=None,
            seed=42,
            nb_output=3,
            img_gen_prompt_var_name=None,
        ),
    )

    TEST_CASES: ClassVar[List[Tuple[str, PipeImgGenBlueprint, str, str, PipeImgGenBlueprintCore]]] = [
        SIMPLE_IMG_GEN,
        IMG_GEN_WITH_OPTIONS,
    ]
