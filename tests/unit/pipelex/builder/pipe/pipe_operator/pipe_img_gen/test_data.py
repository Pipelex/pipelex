from typing import ClassVar

from pipelex.builder.pipe.pipe_img_gen_spec import ImgGenSkill, PipeImgGenSpec
from pipelex.pipe_operators.img_gen.pipe_img_gen_blueprint import PipeImgGenBlueprint


class PipeImgGenTestCases:
    SIMPLE_IMG_GEN = (
        "simple_img_gen",
        PipeImgGenSpec(
            pipe_code="img_generator",
            description="Generate an image",
            inputs={},
            output="GeneratedImage",
            img_gen_skill=ImgGenSkill.GEN_IMAGE_BASIC,
        ),
        PipeImgGenBlueprint(
            description="Generate an image",
            inputs=None,
            output="GeneratedImage",
            type="PipeImgGen",
            pipe_category="PipeOperator",
            img_gen_prompt=None,
            img_gen_prompt_var_name=None,
            model=ImgGenSkill.GEN_IMAGE_BASIC,
            aspect_ratio=None,
            background=None,
            output_format=None,
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
            output="Image[3]",
            img_gen_skill=ImgGenSkill.GEN_IMAGE_FAST,
        ),
        PipeImgGenBlueprint(
            description="Generate image with options",
            inputs={"description": "Text"},
            output="Image[3]",
            type="PipeImgGen",
            pipe_category="PipeOperator",
            img_gen_prompt=None,
            model=ImgGenSkill.GEN_IMAGE_FAST,
            aspect_ratio=None,
            background=None,
            output_format=None,
            is_raw=None,
            seed=None,
            img_gen_prompt_var_name=None,
        ),
    )

    TEST_CASES: ClassVar[list[tuple[str, PipeImgGenSpec, PipeImgGenBlueprint]]] = [
        SIMPLE_IMG_GEN,
        IMG_GEN_WITH_OPTIONS,
    ]
