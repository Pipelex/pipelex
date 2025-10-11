from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.core.concepts.concept_native import NativeConceptEnum
from pipelex.pipe_operators.img_gen.pipe_img_gen_blueprint import PipeImgGenBlueprint

PIPE_IMG_GEN = (
    "pipe_img_gen",
    """domain = "test_pipes"
description = "Domain with image generation pipe"

[pipe.generate_image]
type = "PipeImgGen"
description = "Generate an image from a prompt"
output = "Image"
img_gen_prompt = "A beautiful landscape"
""",
    PipelexBundleBlueprint(
        domain="test_pipes",
        description="Domain with image generation pipe",
        pipe={
            "generate_image": PipeImgGenBlueprint(
                type="PipeImgGen",
                description="Generate an image from a prompt",
                output=NativeConceptEnum.IMAGE,
                img_gen_prompt="A beautiful landscape",
            ),
        },
    ),
)

# Export all PipeImgGen test cases
PIPE_IMG_GEN_TEST_CASES = [
    PIPE_IMG_GEN,
]
