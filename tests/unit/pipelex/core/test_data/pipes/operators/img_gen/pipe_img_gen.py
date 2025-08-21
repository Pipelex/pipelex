"""PipeImgGen test cases."""

from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.pipe_operators.pipe_img_gen_factory import PipeImgGenBlueprint

PIPE_IMG_GEN = (
    "pipe_img_gen",
    """domain = "test_pipes"
definition = "Domain with image generation pipe"

[pipe.generate_image]
type = "PipeImgGen"
definition = "Generate an image from a prompt"
output = "Image"
img_gen_prompt = "A beautiful landscape"
""",
    PipelexBundleBlueprint(
        domain="test_pipes",
        definition="Domain with image generation pipe",
        pipe={
            "generate_image": PipeImgGenBlueprint(
                type="PipeImgGen",
                definition="Generate an image from a prompt",
                output="Image",
                img_gen_prompt="A beautiful landscape",
            ),
        },
    ),
)

# Export all PipeImgGen test cases
PIPE_IMG_GEN_TEST_CASES = [
    PIPE_IMG_GEN,
]
