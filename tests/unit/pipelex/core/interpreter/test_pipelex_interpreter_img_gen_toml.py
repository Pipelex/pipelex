"""Test PipelexInterpreter ImgGen pipe to TOML string conversion."""

import pytest

from pipelex.cogt.imgg.imgg_job_components import AspectRatio
from pipelex.core.interpreter import PipelexInterpreter
from pipelex.pipe_operators.img_gen.pipe_img_gen_blueprint import PipeImgGenBlueprint


class TestPipelexInterpreterImgGenToml:
    """Test ImgGen pipe to TOML string conversion."""

    @pytest.mark.parametrize(
        "pipe_name,blueprint,expected_toml",
        [
            # Basic ImgGen pipe
            (
                "generate_image",
                PipeImgGenBlueprint(
                    type="PipeImgGen",
                    definition="Generate an image from a prompt",
                    output="Image",
                    img_gen_prompt="A beautiful landscape",
                ),
                """[pipe.generate_image]
type = "PipeImgGen"
definition = "Generate an image from a prompt"
output = "Image"
img_gen_prompt = "A beautiful landscape\"""",
            ),
            # ImgGen pipe with some options
            (
                "generate_with_options",
                PipeImgGenBlueprint(
                    type="PipeImgGen",
                    definition="Generate image with options",
                    output="Image",
                    img_gen_prompt="A futuristic city",
                    aspect_ratio=AspectRatio.LANDSCAPE_16_9,
                    seed=12345,
                ),
                """[pipe.generate_with_options]
type = "PipeImgGen"
definition = "Generate image with options"
output = "Image"
img_gen_prompt = "A futuristic city"
aspect_ratio = "landscape_16_9"
seed = 12345""",
            ),
        ],
    )
    def test_img_gen_pipe_to_toml_string(self, pipe_name: str, blueprint: PipeImgGenBlueprint, expected_toml: str):
        """Test converting ImgGen pipe blueprint to TOML string."""
        result = PipelexInterpreter.img_gen_pipe_to_toml_string(pipe_name, blueprint, "test_domain")
        assert result == expected_toml
