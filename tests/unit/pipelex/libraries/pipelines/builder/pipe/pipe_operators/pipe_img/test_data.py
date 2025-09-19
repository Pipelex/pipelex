"""
Test data for PipeImgGenBlueprint conversion tests.
"""

from typing import ClassVar, List, Tuple

from pipelex.cogt.imgg.imgg_handle import ImggHandle
from pipelex.cogt.imgg.imgg_job_components import AspectRatio, Quality
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
            imgg_handle=None,
            aspect_ratio=None,
            quality=None,
            nb_steps=None,
            guidance_scale=None,
            is_moderated=None,
            safety_tolerance=None,
            is_raw=None,
            seed=None,
            nb_output=None,
            img_gen_prompt_var_name=None,
        ),
    )

    IMG_GEN_WITH_OPTIONS = (
        "img_gen_with_options",
        PipeImgGenBlueprint(
            definition="Generate image with options",
            inputs={"description": InputRequirementBlueprint(concept="Text")},
            output="Image",
            imgg_handle=ImggHandle.FLUX_1_PRO_LEGACY,
            aspect_ratio=AspectRatio.SQUARE,
            quality=Quality.HIGH,
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
            imgg_handle=ImggHandle.FLUX_1_PRO_LEGACY,
            aspect_ratio=AspectRatio.SQUARE,
            quality=Quality.HIGH,
            nb_steps=None,
            guidance_scale=None,
            is_moderated=None,
            safety_tolerance=None,
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
