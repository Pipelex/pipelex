from typing import ClassVar

from pipelex.core.pipes.pipe_input_blueprint import InputRequirementBlueprint
from pipelex.libraries.pipelines.builder.pipe.pipe_img_spec import PipeImgGenSpec, RecommendedImgGen
from pipelex.pipe_operators.img_gen.pipe_img_gen_blueprint import PipeImgGenBlueprint


class PipeImgGenTestCases:
    SIMPLE_IMG_GEN = (
        "simple_img_gen",
        PipeImgGenSpec(
            pipe_code="img_generator",
            description="Generate an image",
            inputs={},
            output="GeneratedImage",
        ),
        PipeImgGenBlueprint(
            description="Generate an image",
            inputs=None,
            output="GeneratedImage",
            type="PipeImgGen",
            category="PipeOperator",
            img_gen_prompt=None,
            img_gen_prompt_var_name=None,
            img_gen=None,
            aspect_ratio=None,
            background=None,
            output_format=None,
            nb_output=None,
            is_raw=None,
            seed=None,
        ),
    )

    IMG_GEN_WITH_OPTIONS = (
        "img_gen_with_options",
        PipeImgGenSpec(
            pipe_code="advanced_img_gen",
            description="Generate image with options",
            inputs={"description": "Text"},
            output="Image",
            img_gen=RecommendedImgGen.BASE_IMG_GEN,
            nb_output=3,
        ),
        PipeImgGenBlueprint(
            description="Generate image with options",
            inputs={"description": InputRequirementBlueprint(concept="Text")},
            output="Image",
            type="PipeImgGen",
            category="PipeOperator",
            img_gen_prompt=None,
            img_gen=RecommendedImgGen.BASE_IMG_GEN,
            aspect_ratio=None,
            background=None,
            output_format=None,
            is_raw=None,
            seed=None,
            nb_output=3,
            img_gen_prompt_var_name=None,
        ),
    )

    TEST_CASES: ClassVar[list[tuple[str, PipeImgGenSpec, PipeImgGenBlueprint]]] = [
        SIMPLE_IMG_GEN,
        IMG_GEN_WITH_OPTIONS,
    ]
