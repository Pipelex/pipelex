"""A PipeImgGen whose prompt reads an optional image runs when the image is not given, the shared assembly leaving it out."""

import pytest
from pytest_mock import MockerFixture

from pipelex.cogt.img_gen.img_gen_prompt import ImgGenPrompt
from pipelex.core.stuffs.text_content import TextContent
from pipelex.pipe_operators.img_gen import img_gen_prompt_blueprint
from pipelex.pipeline.runner import PipelexMTHDSProtocol
from pipelex.system.pipe_run_mode import PipeRunMode

_BUNDLE = """
domain = "img_gen_optional_files"
description = "A PipeImgGen whose prompt may hold a reference image"

[pipe.draw_parcel]
type = "PipeImgGen"
description = "Draw a parcel, after a reference photo when one is given"
inputs = { scene = "Text", reference = "Image?" }
output = "Image"
model = "$gen-image-testing-img2img"
prompt = "Draw $scene{% if reference %}, in the style of $reference{% endif %}"
"""


@pytest.mark.asyncio(loop_scope="class")
class TestPipeImgGenOptionalFiles:
    async def test_an_absent_optional_image_is_left_out_of_the_prompt(self, mocker: MockerFixture) -> None:
        assembly_spy = mocker.spy(img_gen_prompt_blueprint, "assemble_img_gen_prompt")

        response = await PipelexMTHDSProtocol(pipe_run_mode=PipeRunMode.DRY).execute(
            mthds_contents=[_BUNDLE],
            pipe_code="draw_parcel",
            inputs={"scene": TextContent(text="a parcel with one corner crushed")},
        )

        img_gen_prompt = assembly_spy.spy_return
        assert isinstance(img_gen_prompt, ImgGenPrompt)
        assert img_gen_prompt.positive_text == "Draw a parcel with one corner crushed"
        assert not img_gen_prompt.input_images
        assert response.pipe_output is not None
