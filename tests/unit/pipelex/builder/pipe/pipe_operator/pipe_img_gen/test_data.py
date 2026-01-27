from typing import ClassVar

from pipelex.builder.pipe.pipe_img_gen_spec import PipeImgGenSpec
from pipelex.builder.talents.img_gen_talent import ImgGenTalent
from pipelex.pipe_operators.img_gen.pipe_img_gen_blueprint import PipeImgGenBlueprint


class PipeImgGenTestCases:
    SIMPLE_IMG_GEN = (
        "simple_img_gen",
        PipeImgGenSpec(
            pipe_code="img_generator",
            description="Generate an image",
            inputs={"my_prompt": "Text"},
            output="native.Image",
            img_gen_talent=ImgGenTalent.GEN_IMAGE,
            prompt="@my_prompt",
        ),
        PipeImgGenBlueprint(
            description="Generate an image",
            inputs={"my_prompt": "Text"},
            output="native.Image",
            prompt="@my_prompt",
            model="$gen-image",
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
            prompt="@description",
            img_gen_talent=ImgGenTalent.GEN_IMAGE_FAST,
        ),
        PipeImgGenBlueprint(
            description="Generate image with options",
            inputs={"description": "Text"},
            output="Image[3]",
            prompt="@description",
            model="$gen-image-fast",
            aspect_ratio=None,
            background=None,
            output_format=None,
            is_raw=None,
            seed=None,
        ),
    )

    TEST_CASES: ClassVar[list[tuple[str, PipeImgGenSpec, PipeImgGenBlueprint]]] = [
        SIMPLE_IMG_GEN,
        IMG_GEN_WITH_OPTIONS,
    ]
